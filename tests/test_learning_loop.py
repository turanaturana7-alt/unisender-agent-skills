import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "unisender-skill-factory" / "scripts" / "learning_loop.py"
RELEASE_SCRIPT = ROOT / "skills" / "unisender-skill-factory" / "scripts" / "release.py"
EVAL_SCRIPT = ROOT / "skills" / "unisender-skill-factory" / "scripts" / "eval_runner.py"
EVAL_CASES = ROOT / "skills" / "unisender-skill-factory" / "evals" / "cases.json"


def load_module():
    spec = importlib.util.spec_from_file_location("learning_loop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def load_release_module():
    spec = importlib.util.spec_from_file_location("release", RELEASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def load_eval_module():
    spec = importlib.util.spec_from_file_location("eval_runner", EVAL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class LearningLoopTests(unittest.TestCase):
    def test_semantic_version_bumps(self):
        module = load_release_module()
        self.assertEqual("1.2.4", module.bump_version("1.2.3", "patch"))
        self.assertEqual("1.3.0", module.bump_version("1.2.3", "minor"))
        self.assertEqual("2.0.0", module.bump_version("1.2.3", "major"))

    def test_sensitive_data_is_detected(self):
        module = load_module()
        email = "real.person" + "@company.ru"
        token = "Authorization: " + "Bearer " + "abcdefghijklmnop"
        self.assertIn("email address", module.find_sensitive(f"subscriber: {email}"))
        self.assertIn("bearer token", module.find_sensitive(token))
        github_token = "gh" + "p_" + ("a" * 24)
        self.assertIn("GitHub token", module.find_sensitive(github_token))

    def test_example_email_is_allowed(self):
        module = load_module()
        self.assertNotIn("email address", module.find_sensitive("Use example@example.com"))

    def test_two_distinct_tasks_make_pattern_ready(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            for fingerprint in ("task-a", "task-b"):
                verification = "artifact-qa" if fingerprint == "task-a" else "interface"
                args = SimpleNamespace(
                    pattern_key="editor-readback",
                    problem="Visual edits can transform source markup",
                    solution="Read back and diff the transformed copy",
                    task_fingerprint=fingerprint,
                    verified_by=verification,
                    before="The transformed source had an unexplained structural diff",
                    after="Only the intentional structural diff remained",
                    evidence=["The intentional diff passed structural checks"],
                    limitation=["This does not prove delivery-client rendering"],
                    state_dir=directory,
                )
                self.assertEqual(0, module.capture(args))

            data = module.grouped_status(Path(directory))
            self.assertTrue(data[0]["ready"])
            self.assertEqual(2, data[0]["distinct_tasks"])
            self.assertEqual(5, data[0]["evidence_score"])

    def test_two_weak_confirmations_are_not_ready(self):
        module = load_module()
        records = [
            {
                "task_fingerprint": "a",
                "verified_by": "user-confirmation",
                "evidence_score": 1,
                "before": "before",
                "after": "after",
                "limitations": ["not technically checked"],
            },
            {
                "task_fingerprint": "b",
                "verified_by": "user-confirmation",
                "evidence_score": 1,
                "before": "before",
                "after": "after",
                "limitations": ["not technically checked"],
            },
        ]
        evaluation = module.evaluate_pattern(records)
        self.assertFalse(evaluation["ready"])
        self.assertIn("needs at least one technical verification", evaluation["reasons"])

    def test_eval_cases_are_valid(self):
        module = load_eval_module()
        cases = module.load_cases(EVAL_CASES)
        self.assertGreaterEqual(len(cases), 6)
        self.assertIn("negative", {case["routing"] for case in cases})

    def test_release_metadata_does_not_change_behavior_hash(self):
        module = load_eval_module()
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: sample\ndescription: sample\n---\n", encoding="utf-8")
            (skill / "VERSION").write_text("0.1.0\n", encoding="utf-8")
            first = module.skill_hash(skill)
            (skill / "VERSION").write_text("0.2.0\n", encoding="utf-8")
            (skill / "CHANGELOG.md").write_text("changed\n", encoding="utf-8")
            self.assertEqual(first, module.skill_hash(skill))


if __name__ == "__main__":
    unittest.main()
