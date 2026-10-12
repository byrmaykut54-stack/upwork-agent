import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def test_both_documented_entry_points_export_safe_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "drafts.json"
            for entry in (["-m", "agent.main"], ["agent/main.py"]):
                result = subprocess.run([sys.executable, *entry, "--jobs", "agent/jobs.example.json", "--connects-balance", "10", "--output", str(output)], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                drafts = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(len(drafts), 1)
                self.assertFalse(drafts[0]["eligible_for_submission"])
                self.assertIn("fictional", drafts[0]["title"].lower())
                self.assertNotIn("Verified experience", drafts[0]["proposal"])

    def test_invalid_input_has_readable_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Path(directory) / "jobs.json"
            for value in ({"jobs": []}, [None], "invalid json"):
                jobs.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
                result = subprocess.run([sys.executable, "-m", "agent.main", "--jobs", str(jobs)], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_selected_missing_profile_is_rejected(self):
        result = subprocess.run([sys.executable, "-m", "agent.main", "--jobs", "agent/jobs.example.json", "--profile", "not-present-profile.json"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("profile file does not exist", result.stderr)
