#!/usr/bin/env python3
"""Capture and review sanitized UniSender learning evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SENSITIVE_PATTERNS = {
    "secret": re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|authorization)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    "bearer token": re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "email address": re.compile(r"(?i)\b(?!example@example\.com\b)[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+\b"),
    "russian phone": re.compile(r"(?<!\d)(?:\+7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"),
    "credential in URL": re.compile(r"(?i)https?://[^\s]+[?&](?:token|key|secret|auth)=[^\s&#]+"),
    "local user path": re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+\\"),
}

TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".py", ".js", ".ts",
    ".html", ".css", ".xml", ".toml", ".ini", ".cfg", ".ps1", "",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def state_dir(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    configured = os.environ.get("UNISENDER_SKILL_STATE_DIR")
    return Path(configured).resolve() if configured else (Path.cwd() / ".skill-learning").resolve()


def find_sensitive(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


def require_safe(label: str, value: str) -> None:
    findings = find_sensitive(value)
    if findings:
        raise ValueError(f"{label} contains blocked data patterns: {', '.join(findings)}")


def load_records(root: Path) -> list[dict]:
    records = []
    for path in sorted((root / "records").glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return records


def capture(args: argparse.Namespace) -> int:
    labeled = [
        ("pattern key", args.pattern_key),
        ("problem", args.problem),
        ("solution", args.solution),
        ("task fingerprint", args.task_fingerprint),
        *[("evidence", item) for item in args.evidence],
    ]
    for label, value in labeled:
        require_safe(label, value)

    root = state_dir(args.state_dir)
    records_dir = root / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    record_id = f"{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
    fingerprint = hashlib.sha256(args.task_fingerprint.encode("utf-8")).hexdigest()[:16]
    record = {
        "schema_version": 1,
        "id": record_id,
        "created_at": utc_now(),
        "pattern_key": args.pattern_key,
        "problem": args.problem,
        "solution": args.solution,
        "task_fingerprint": fingerprint,
        "verified_by": args.verified_by,
        "evidence": args.evidence,
        "status": "candidate",
    }
    path = records_dir / f"{record_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "captured", "id": record_id, "path": str(path)}, ensure_ascii=False))
    return 0


def grouped_status(root: Path) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in load_records(root):
        grouped[record["pattern_key"]].append(record)
    result = []
    for pattern_key, records in sorted(grouped.items()):
        fingerprints = {record["task_fingerprint"] for record in records}
        result.append({
            "pattern_key": pattern_key,
            "records": len(records),
            "distinct_tasks": len(fingerprints),
            "ready": len(fingerprints) >= 2,
            "statuses": sorted({record["status"] for record in records}),
        })
    return result


def status(args: argparse.Namespace) -> int:
    print(json.dumps(grouped_status(state_dir(args.state_dir)), ensure_ascii=False, indent=2))
    return 0


def propose(args: argparse.Namespace) -> int:
    require_safe("skill name", args.skill_name)
    require_safe("summary", args.summary)
    root = state_dir(args.state_dir)
    records = [record for record in load_records(root) if record["pattern_key"] == args.pattern_key]
    distinct = {record["task_fingerprint"] for record in records}
    if not records:
        raise ValueError(f"no records found for pattern: {args.pattern_key}")
    if len(distinct) < 2 and not args.user_approved:
        raise ValueError("promotion needs two distinct successful tasks or --user-approved")

    proposals = root / "proposals"
    proposals.mkdir(parents=True, exist_ok=True)
    proposal_id = f"{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
    proposal = {
        "schema_version": 1,
        "id": proposal_id,
        "created_at": utc_now(),
        "pattern_key": args.pattern_key,
        "target_skill": args.skill_name,
        "summary": args.summary,
        "evidence_record_ids": [record["id"] for record in records],
        "early_user_approval": bool(args.user_approved and len(distinct) < 2),
        "status": "proposal",
    }
    path = proposals / f"{proposal_id}.json"
    path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "proposal prepared", "id": proposal_id, "path": str(path)}, ensure_ascii=False))
    return 0


def audit_public(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    findings: list[dict] = []
    excluded = {".git", ".skill-learning", "__pycache__", ".pytest_cache"}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for finding in find_sensitive(text):
            findings.append({"file": str(path.relative_to(root)), "finding": finding})
    if findings:
        print(json.dumps({"status": "blocked", "findings": findings}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "public audit passed", "files_root": str(root)}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    capture_parser = sub.add_parser("capture", help="Capture one verified, sanitized success")
    capture_parser.add_argument("--pattern-key", required=True)
    capture_parser.add_argument("--problem", required=True)
    capture_parser.add_argument("--solution", required=True)
    capture_parser.add_argument("--task-fingerprint", required=True)
    capture_parser.add_argument("--verified-by", required=True, choices=["artifact-qa", "interface", "delivery-test", "user-confirmation"])
    capture_parser.add_argument("--evidence", required=True, action="append")
    capture_parser.add_argument("--state-dir")
    capture_parser.set_defaults(func=capture)

    status_parser = sub.add_parser("status", help="List evidence counts and promotion readiness")
    status_parser.add_argument("--state-dir")
    status_parser.set_defaults(func=status)

    propose_parser = sub.add_parser("propose", help="Prepare a private skill proposal")
    propose_parser.add_argument("--pattern-key", required=True)
    propose_parser.add_argument("--skill-name", required=True)
    propose_parser.add_argument("--summary", required=True)
    propose_parser.add_argument("--user-approved", action="store_true")
    propose_parser.add_argument("--state-dir")
    propose_parser.set_defaults(func=propose)

    audit_parser = sub.add_parser("audit-public", help="Block obvious secrets and personal data in public files")
    audit_parser.add_argument("--repo-root", default=".")
    audit_parser.set_defaults(func=audit_public)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
