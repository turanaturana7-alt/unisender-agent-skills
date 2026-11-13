#!/usr/bin/env python3
"""Version, validate, and optionally publish one skill release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--bump", required=True, choices=["patch", "minor", "major"])
    parser.add_argument("--summary", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    skill_dir = root / "skills" / args.skill
    version_path = skill_dir / "VERSION"
    changelog_path = skill_dir / "CHANGELOG.md"
    catalog_path = root / "catalog.json"
    if not version_path.exists():
        raise ValueError(f"missing {version_path}")

    validate_skill(skill_dir)
    current = version_path.read_text(encoding="utf-8").strip()
    new_version = bump_version(current, args.bump)
    version_path.write_text(new_version + "\n", encoding="utf-8")

    previous = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else "# Changelog\n"
    header, _, remainder = previous.partition("\n")
    entry = f"\n## {new_version} — {date.today().isoformat()}\n\n- {args.summary.strip()}\n"
    changelog_path.write_text(header + entry + ("\n" + remainder.lstrip("\n") if remainder else ""), encoding="utf-8")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog.setdefault("skills", {}).setdefault(args.skill, {})["version"] = new_version
    catalog["skills"][args.skill]["path"] = f"skills/{args.skill}"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    loop_script = skill_dir / "scripts" / "learning_loop.py"
    run([sys.executable, str(loop_script), "audit-public", "--repo-root", str(root)], root)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], root)

    tag = f"{args.skill}-v{new_version}"
    if args.publish:
        run(["git", "add", f"skills/{args.skill}/VERSION", f"skills/{args.skill}/CHANGELOG.md", "catalog.json"], root)
        run(["git", "commit", "-m", f"release({args.skill}): v{new_version}"], root)
        run(["git", "tag", "-a", tag, "-m", f"{args.skill} v{new_version}"], root)
        run(["git", "push", "origin", "HEAD"], root)
        run(["git", "push", "origin", tag], root)

    print(json.dumps({"status": "released" if args.publish else "versioned", "skill": args.skill, "version": new_version, "tag": tag}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        sys.exit(2)
