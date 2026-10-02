import unittest

from agent.pipeline import run_pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "min_hourly_rate_usd": 15,
            "min_fixed_budget_usd": 100,
            "max_proposals_to_consider": 20,
            "prefer_verified_payment": True,
            "keywords": ["excel", "google sheets", "automation"],
            "exclude_keywords": ["gambling", "illegal"],
        }
        self.profile = {
            "relevant_experience": ["Excel automation", "Google Sheets automation"],
            "proof": "Built a 6-in-1 automated Excel toolkit.",
            "language": "English - Basic",
        }

    def test_pipeline_blocks_when_connects_are_insufficient(self):
        raw = [{
            "id": "1",
            "title": "Excel automation",
            "description": "Automate a reporting workbook",
            "skills": ["Microsoft Excel"],
            "hourlyRate": {"min": 18, "max": 25},
            "client": {"paymentVerified": True, "totalHires": 2},
            "proposalsCount": 5,
            "connectsCost": 8,
            "can_apply": True,
        }]
        result = run_pipeline(raw, self.config, self.profile, connects_balance=0)
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["eligibility"]["eligible_for_preview"])
        self.assertIn("Insufficient Connects", result[0]["eligibility"]["reasons"])
        self.assertFalse(result[0]["eligibility"]["eligible_for_submission"])

    def test_pipeline_never_invents_profile_evidence(self):
        raw = [{
            "id": "2",
            "title": "Excel dashboard",
            "description": "Build a dashboard",
            "skills": ["Microsoft Excel"],
            "hourlyRate": {"min": 18, "max": 25},
            "client": {"paymentVerified": True},
            "proposalsCount": 3,
            "connectsCost": 1,
            "can_apply": True,
        }]
        result = run_pipeline(raw, self.config, self.profile, connects_balance=10)
        proposal = result[0]["proposal_preview"]
        self.assertIn("6-in-1 automated Excel toolkit", proposal)
        self.assertNotIn("10 years", proposal)

    def test_pipeline_blocks_low_budget(self):
        raw = [{
            "id": "3",
            "title": "Excel automation",
            "description": "Automate a workbook",
            "skills": ["Microsoft Excel"],
            "hourlyRate": {"min": 10, "max": 12},
            "client": {"paymentVerified": True},
            "proposalsCount": 2,
            "connectsCost": 1,
            "can_apply": True,
        }]
        result = run_pipeline(raw, self.config, self.profile, connects_balance=10)
        self.assertFalse(result[0]["eligibility"]["eligible_for_preview"])
        self.assertIn("Hourly rate below configured minimum", result[0]["eligibility"]["reasons"])


if __name__ == "__main__":
    unittest.main()
