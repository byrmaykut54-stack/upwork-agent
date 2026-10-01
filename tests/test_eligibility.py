import unittest
from agent.eligibility import apply_gate


class EligibilityTests(unittest.TestCase):
    def test_zero_connects_blocks_submission(self):
        job = {"can_apply": True, "connects_cost": 8, "score": 80}
        result = apply_gate(job, 0)
        self.assertFalse(result["eligible_for_preview"])
        self.assertIn("Insufficient Connects", result["reasons"])
        self.assertFalse(result["eligible_for_submission"])

    def test_user_confirmation_always_required(self):
        job = {"can_apply": True, "connects_cost": 1, "score": 80}
        result = apply_gate(job, 10)
        self.assertTrue(result["eligible_for_preview"])
        self.assertTrue(result["requires_user_confirmation"])
        self.assertFalse(result["eligible_for_submission"])


if __name__ == "__main__":
    unittest.main()
