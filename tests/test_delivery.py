import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from scripts.package_offline import build


class DeliveryTests(unittest.TestCase):
    def test_delivery_runs_from_clean_extraction_and_contains_no_private_data(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = build(Path(directory) / 'delivery.zip')
            with ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                self.assertFalse(any(name.endswith(('profile.json', 'jobs.json', '.env')) for name in names))
                archive.extractall(Path(directory) / 'buyer')
            buyer = Path(directory) / 'buyer' / 'MexAy_Job_Draft_Assistant'
            result = subprocess.run([sys.executable, '-m', 'agent.main', '--jobs', 'agent/jobs.example.json', '--connects-balance', '10'], cwd=buyer, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)[0]['eligible_for_submission'])
            self.assertTrue(archive_path.with_suffix('.sha256').exists())
