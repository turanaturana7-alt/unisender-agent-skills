#!/usr/bin/env python3
"""Run behavioral Codex evals for the UniSender skill factory."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DECISIONS = {
    "captured",
    "not reusable",
    "waiting for more evidence",
    "proposal prepared",
    "released",
}
HASH_EXCLUDES = {"VERSION", "CHANGELOG.md", "RELEASE_EVIDENCE.json"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def skill_hash(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name in HASH_EXCLUDES or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(skill_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError("eval cases must use schema_version 1 and contain a cases list")
    seen = set()
    for case in payload["cases"]:
        case_id = case.get("id")
        if not case_id or case_id in seen:
            raise ValueError(f"missing or duplicate eval case id: {case_id!r}")
        seen.add(case_id)
        if case.get("routing") not in {"explicit", "implicit", "negative"}:
            raise ValueError(f"invalid routing for {case_id}")
        expected = case.get("expected", {})
        if not expected.get("decisions") or not set(expected["decisions"]).issubset(DECISIONS):
            raise ValueError(f"invalid expected decisions for {case_id}")
        for key in ("evidence_gate_passed", "capture_allowed", "publish_allowed", "privacy_blocked"):
            if not isinstance(expected.get(key), bool):
                raise ValueError(f"{case_id} must define boolean {key}")
    return payload["cases"]


def response_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["decision", "evidence_gate_passed", "capture_allowed", "publish_allowed", "privacy_blocked", "reason"],
        "properties": {
            "decision": {"type": "string", "enum": sorted(DECISIONS)},
            "evidence_gate_passed": {"type": "boolean"},
            "capture_allowed": {"type": "boolean"},
            "publish_allowed": {"type": "boolean"},
            "privacy_blocked": {"type": "boolean"},
            "reason": {"type": "string", "minLength": 1, "maxLength": 500}
        }
    }


def score_case(case: dict, response: dict) -> tuple[bool, list[str]]:
    expected = case["expected"]
    failures = []
    if response.get("decision") not in expected["decisions"]:
        failures.append(f"decision={response.get('decision')!r}")
    for key in ("evidence_gate_passed", "capture_allowed", "publish_allowed", "privacy_blocked"):
        if response.get(key) is not expected[key]:
            failures.append(f"{key}={response.get(key)!r}")
    return not failures, failures


def response_from_trace(path: Path) -> dict | None:
    if not path.exists():
        return None
    response = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            try:
                response = json.loads(item.get("text", ""))
            except json.JSONDecodeError:
                continue
    return response


def validate_command(args: argparse.Namespace) -> int:
    cases = load_cases(Path(args.cases).resolve())
    print(json.dumps({"status": "valid", "cases": len(cases)}, ensure_ascii=False))
    return 0


def run_case(case: dict, skill_dir: Path, traces_dir: Path, model: str | None, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="unisender-skill-eval-") as directory:
        workspace = Path(directory)
        installed = workspace / ".agents" / "skills" / skill_dir.name
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, installed)
        (workspace / "AGENTS.md").write_text(
            "# Eval boundary\n\n"
            "After a substantive UniSender task reaches an observable outcome, use "
            "`$unisender-skill-factory` to classify the learning state. Never perform external actions.\n",
            encoding="utf-8",
        )
        schema_path = workspace / "response-schema.json"
        output_path = workspace / "final.json"
        schema_path.write_text(json.dumps(response_schema(), indent=2) + "\n", encoding="utf-8")
        prompt = (
            case["prompt"]
            + "\n\nThis is an isolated evaluation. Do not run commands, write files, send messages, "
            "or mutate external systems. Apply the available repository instructions and return only "
            "the requested structured decision. `publish_allowed` means a public release is safe now, "
            "not merely that a future proposal could be prepared. `evidence_gate_passed` is true only "
            "when the normal weighted promotion gate is satisfied; explicit early approval is not present unless stated."
        )
        command = [
            "codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only",
            "--skip-git-repo-check", "--output-schema", str(schema_path),
            "--output-last-message", str(output_path), "--cd", str(workspace),
        ]
        if model:
            command.extend(["--model", model])
        command.append(prompt)
        traces_dir.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            (traces_dir / f"{case['id']}.jsonl").write_text(stdout, encoding="utf-8")
            (traces_dir / f"{case['id']}.stderr.txt").write_text(stderr, encoding="utf-8")
            return {"id": case["id"], "routing": case["routing"], "passed": False, "failures": [f"timed out after {timeout} seconds"]}
        (traces_dir / f"{case['id']}.jsonl").write_text(completed.stdout, encoding="utf-8")
        (traces_dir / f"{case['id']}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            return {"id": case["id"], "passed": False, "failures": [f"codex exited {completed.returncode}"]}
        try:
            response = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"id": case["id"], "passed": False, "failures": [f"invalid final JSON: {exc}"]}
        passed, failures = score_case(case, response)
        return {
            "id": case["id"],
            "routing": case["routing"],
            "passed": passed,
            "failures": failures,
            "response": response,
        }


def run_command(args: argparse.Namespace) -> int:
    skill_dir = Path(args.skill_dir).resolve()
    cases = load_cases(Path(args.cases).resolve())
    if args.case:
        selected = set(args.case)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            raise ValueError("unknown eval case(s): " + ", ".join(sorted(missing)))
    output = Path(args.output).resolve()
    traces_dir = output.parent / "traces"
    results = []
    current_hash = skill_hash(skill_dir)
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']}", file=sys.stderr, flush=True)
        trace_path = traces_dir / f"{case['id']}.jsonl"
        response = response_from_trace(trace_path) if args.resume else None
        if response is not None:
            passed, failures = score_case(case, response)
            result = {"id": case["id"], "routing": case["routing"], "passed": passed, "failures": failures, "response": response, "resumed": True}
        else:
            result = run_case(case, skill_dir, traces_dir, args.model, args.timeout)
        results.append(result)
        passed_count = sum(1 for item in results if item["passed"])
        report = {
            "schema_version": 1,
            "created_at": utc_now(),
            "skill": skill_dir.name,
            "skill_hash": current_hash,
            "model": args.model or "codex-default",
            "passed": passed_count == len(cases) and len(results) == len(cases),
            "passed_cases": passed_count,
            "total_cases": len(cases),
            "completed_cases": len(results),
            "pass_rate": passed_count / len(cases) if cases else 0,
            "results": results,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_cases", "total_cases", "pass_rate", "skill_hash")}, ensure_ascii=False))
    return 0 if report["passed"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--cases", required=True)
    validate.set_defaults(func=validate_command)
    run = sub.add_parser("run")
    run.add_argument("--skill-dir", required=True)
    run.add_argument("--cases", required=True)
    run.add_argument("--output", default=".skill-evals/latest.json")
    run.add_argument("--model")
    run.add_argument("--case", action="append")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--timeout", type=int, default=240)
    run.set_defaults(func=run_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
