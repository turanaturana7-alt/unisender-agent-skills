#!/usr/bin/env python3
"""Capture and review sanitized UniSender learning evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
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
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "password or cookie": re.compile(r"(?i)(password|passwd|cookie|session[_-]?id|webhook[_-]?secret)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
}

TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".py", ".js", ".ts",
    ".html", ".css", ".xml", ".toml", ".ini", ".cfg", ".ps1", "",
}

EVIDENCE_WEIGHTS = {
    "user-confirmation": 1,
    "artifact-qa": 2,
    "interface": 3,
    "delivery-test": 4,
}
TECHNICAL_VERIFICATIONS = {"artifact-qa", "interface", "delivery-test"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def state_dir(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    configured = os.environ.get("UNISENDER_SKILL_STATE_DIR")
    if configured:
        return Path(configured).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "Codex" / "unisender-skill-evidence").resolve()
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return (Path(xdg_state) / "codex" / "unisender-skill-evidence").resolve()
    return (Path.cwd() / ".skill-learning").resolve()


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
        ("before state", args.before),
        ("after state", args.after),
        *[("evidence", item) for item in args.evidence],
        *[("limitation", item) for item in args.limitation],
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
        "evidence_score": EVIDENCE_WEIGHTS[args.verified_by],
        "before": args.before,
        "after": args.after,
        "evidence": args.evidence,
        "limitations": args.limitation,
        "status": "candidate",
    }
    path = records_dir / f"{record_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "captured", "id": record_id, "path": str(path)}, ensure_ascii=False))
    return 0


def evaluate_pattern(records: list[dict]) -> dict:
    fingerprints = {record["task_fingerprint"] for record in records}
    score = sum(int(record.get("evidence_score", EVIDENCE_WEIGHTS.get(record.get("verified_by"), 0))) for record in records)
    technical = sum(1 for record in records if record.get("verified_by") in TECHNICAL_VERIFICATIONS)
    reasons = []
    if len(fingerprints) < 2:
        reasons.append("needs two distinct tasks")
    if score < 5:
        reasons.append("needs evidence score of at least 5")
    if technical < 1:
        reasons.append("needs at least one technical verification")
    if any(not record.get("before") or not record.get("after") for record in records):
        reasons.append("needs before and after state for every record")
    if any(not record.get("limitations") for record in records):
        reasons.append("needs a known limitation for every record")
    return {
        "distinct_tasks": len(fingerprints),
        "evidence_score": score,
        "technical_verifications": technical,
        "ready": not reasons,
        "reasons": reasons,
    }


def grouped_status(root: Path) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in load_records(root):
        grouped[record["pattern_key"]].append(record)
    result = []
    for pattern_key, records in sorted(grouped.items()):
        evaluation = evaluate_pattern(records)
        result.append({
            "pattern_key": pattern_key,
            "records": len(records),
            "statuses": sorted({record["status"] for record in records}),
            **evaluation,
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
    if not records:
        raise ValueError(f"no records found for pattern: {args.pattern_key}")
    evaluation = evaluate_pattern(records)
    if not evaluation["ready"] and not args.user_approved:
        raise ValueError("promotion gate failed: " + "; ".join(evaluation["reasons"]))
    if args.user_approved and not evaluation["ready"]:
        if evaluation["technical_verifications"] < 1 or evaluation["evidence_score"] < 2:
            raise ValueError("early user-approved proposal still needs one technical verification and score at least 2")

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
        "evidence_summary": evaluation,
        "early_user_approval": bool(args.user_approved and not evaluation["ready"]),
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
    if (root / ".git").exists():
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        paths = [root / relative for relative in listed]
    else:
        paths = list(root.rglob("*"))
    for path in paths:
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
    capture_parser.add_argument("--before", required=True)
    capture_parser.add_argument("--after", required=True)
    capture_parser.add_argument("--evidence", required=True, action="append")
    capture_parser.add_argument("--limitation", required=True, action="append")
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
