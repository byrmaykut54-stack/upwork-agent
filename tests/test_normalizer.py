import unittest
from agent.job_normalizer import normalize_job


class NormalizerTests(unittest.TestCase):
    def test_normalizes_nested_job(self):
        raw = {"data": {"marketplaceJobPosting": {
            "id": 123,
            "title": "Google Sheets automation",
            "description": "Automate reporting",
            "skills": [{"name": "Google Sheets"}, {"name": "Python"}],
            "hourlyRate": {"min": 15, "max": 30},
            "client": {"paymentVerified": True, "totalHires": 4, "rating": 4.9},
            "proposalsCount": 7,
            "connectsCost": 8,
        }}}
        job = normalize_job(raw)
        self.assertEqual(job["id"], 123)
        self.assertEqual(job["skills"], ["Google Sheets", "Python"])
        self.assertEqual(job["hourly_rate_max"], 30.0)
        self.assertEqual(job["proposals_count"], 7)
        self.assertTrue(job["payment_verified"])


if __name__ == "__main__":
    unittest.main()
