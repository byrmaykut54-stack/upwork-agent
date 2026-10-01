import unittest
from agent.scorer import score_job

CONFIG = {
    "min_hourly_rate_usd": 15,
    "min_fixed_budget_usd": 100,
    "prefer_verified_payment": True,
    "keywords": ["automation", "google sheets", "excel", "python"],
    "exclude_keywords": ["gambling", "illegal"],
}

class ScorerTests(unittest.TestCase):
    def test_relevant_verified_job_scores(self):
        job = {"title": "Excel and Google Sheets automation", "description": "Build an automated dashboard with Python", "hourly_rate_max": 25, "payment_verified": True, "proposals_count": 5, "client_hires": 3}
        result = score_job(job, CONFIG)
        self.assertGreaterEqual(result["score"], 70)

    def test_excluded_job_scores_zero(self):
        result = score_job({"title": "Gambling spreadsheet automation"}, CONFIG)
        self.assertEqual(result["score"], 0)
        self.assertIn("excluded keyword", result["risks"])

if __name__ == "__main__":
    unittest.main()
