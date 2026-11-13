import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "unisender-skill-factory" / "scripts" / "learning_loop.py"
RELEASE_SCRIPT = ROOT / "skills" / "unisender-skill-factory" / "scripts" / "release.py"


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

    def test_example_email_is_allowed(self):
        module = load_module()
        self.assertNotIn("email address", module.find_sensitive("Use example@example.com"))

    def test_two_distinct_tasks_make_pattern_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            for fingerprint in ("task-a", "task-b"):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "capture",
                        "--pattern-key", "editor-readback",
                        "--problem", "Visual edits can transform source markup",
                        "--solution", "Read back and diff the transformed copy",
                        "--task-fingerprint", fingerprint,
                        "--verified-by", "artifact-qa",
                        "--evidence", "The intentional diff passed structural checks",
                        "--state-dir", directory,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual("captured", json.loads(result.stdout)["status"])

            status = subprocess.run(
                [sys.executable, str(SCRIPT), "status", "--state-dir", directory],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(status.stdout)
            self.assertTrue(data[0]["ready"])
            self.assertEqual(2, data[0]["distinct_tasks"])


if __name__ == "__main__":
    unittest.main()
