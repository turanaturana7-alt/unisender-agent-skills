#!/usr/bin/env python3
"""Version, validate, and open a protected skill release pull request."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
MAX_EVAL_AGE_HOURS = 24


def run(command: list[str], cwd: Path, capture: bool = False) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def bump_version(current: str, bump: str) -> str:
    match = VERSION_RE.fullmatch(current.strip())
    if not match:
        raise ValueError(f"invalid semantic version: {current!r}")
    major, minor, patch = map(int, match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def validate_skill(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"missing {skill_md}")
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\nname:" not in text or "\ndescription:" not in text:
        raise ValueError(f"invalid frontmatter in {skill_md}")
    if "TODO" in text:
        raise ValueError(f"unfinished TODO in {skill_md}")


def load_eval_report(report_path: Path, skill_dir: Path) -> dict:
    if not report_path.exists():
        raise ValueError(f"missing behavioral eval report: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report.get("passed"):
        raise ValueError("behavioral eval report did not pass")
    if report.get("skill") != skill_dir.name:
        raise ValueError("behavioral eval report targets another skill")

    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from eval_runner import skill_hash
    finally:
        sys.path.pop(0)
    current_hash = skill_hash(skill_dir)
    if report.get("skill_hash") != current_hash:
        raise ValueError("behavioral eval report is stale for the current skill hash")

    created = datetime.fromisoformat(report["created_at"].replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - created.astimezone(timezone.utc)
    if age.total_seconds() > MAX_EVAL_AGE_HOURS * 3600:
        raise ValueError(f"behavioral eval report is older than {MAX_EVAL_AGE_HOURS} hours")
    return report


def ensure_release_branch(root: Path, tag: str) -> str:
    target = f"codex/release/{tag}"
    current = run(["git", "branch", "--show-current"], root, capture=True)
    if current == target:
        return target
    run(["git", "switch", "-c", target], root)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--bump", required=True, choices=["patch", "minor", "major"])
    parser.add_argument("--summary", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--eval-report", default=".skill-evals/latest.json")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--approve-nonpatch", action="store_true")
    args = parser.parse_args()

    if args.publish and args.bump != "patch" and not args.approve_nonpatch:
        raise ValueError("minor and major publication require explicit --approve-nonpatch")

    root = Path(args.repo_root).resolve()
    skill_dir = root / "skills" / args.skill
    version_path = skill_dir / "VERSION"
    changelog_path = skill_dir / "CHANGELOG.md"
    catalog_path = root / "catalog.json"
    eval_path = (root / args.eval_report).resolve()
    if not version_path.exists():
        raise ValueError(f"missing {version_path}")

    validate_skill(skill_dir)
    eval_report = load_eval_report(eval_path, skill_dir)
    current = version_path.read_text(encoding="utf-8").strip()
    new_version = bump_version(current, args.bump)
    tag = f"{args.skill}-v{new_version}"

    version_path.write_text(new_version + "\n", encoding="utf-8")
    previous = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else "# Changelog\n"
    header, _, remainder = previous.partition("\n")
    entry = f"\n## {new_version} — {date.today().isoformat()}\n\n- {args.summary.strip()}\n"
    changelog_path.write_text(header + entry + ("\n" + remainder.lstrip("\n") if remainder else ""), encoding="utf-8")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog.setdefault("skills", {}).setdefault(args.skill, {})["version"] = new_version
    catalog["skills"][args.skill]["path"] = f"skills/{args.skill}"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evidence = {
        "schema_version": 1,
        "version": new_version,
        "skill_hash": eval_report["skill_hash"],
        "evaluated_at": eval_report["created_at"],
        "model": eval_report["model"],
        "passed_cases": eval_report["passed_cases"],
        "total_cases": eval_report["total_cases"],
        "pass_rate": eval_report["pass_rate"],
    }
    (skill_dir / "RELEASE_EVIDENCE.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    loop_script = skill_dir / "scripts" / "learning_loop.py"
    eval_script = skill_dir / "scripts" / "eval_runner.py"
    cases_path = skill_dir / "evals" / "cases.json"
    run([sys.executable, str(loop_script), "audit-public", "--repo-root", str(root)], root)
    run([sys.executable, str(eval_script), "validate", "--cases", str(cases_path)], root)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], root)

    if not args.publish:
        print(json.dumps({"status": "versioned", "skill": args.skill, "version": new_version, "tag": tag}))
        return 0

    branch = ensure_release_branch(root, tag)
    run(["git", "add", "--", f"skills/{args.skill}", "catalog.json", "tests", ".github/workflows", ".gitignore", "AGENTS.md", "README.md"], root)
    run(["git", "commit", "-m", f"release({args.skill}): v{new_version}"], root)
    run(["git", "push", "-u", "origin", branch], root)
    body = (
        f"## Release\n\n- Skill: `{args.skill}`\n- Version: `{new_version}`\n"
        f"- Behavioral evals: {eval_report['passed_cases']}/{eval_report['total_cases']} passed\n"
        f"- Skill hash: `{eval_report['skill_hash']}`\n\n"
        "The merged release PR will create the tag and GitHub Release automatically."
    )
    pr_url = run(
        ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", f"release({args.skill}): v{new_version}", "--body", body],
        root,
        capture=True,
    )
    run(["gh", "pr", "merge", "--auto", "--merge", "--delete-branch", pr_url], root)
    print(json.dumps({"status": "proposal prepared", "skill": args.skill, "version": new_version, "tag": tag, "pr": pr_url}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        sys.exit(2)
