import unittest
from agent.eligibility import apply_gate


class EligibilityTests(unittest.TestCase):
    def test_zero_connects_blocks_submission(self):
        job = {"can_apply": True, "connects_cost": 8, "score": 80}
        result = apply_gate(job, 0, {"min_hourly_rate_usd": 15, "min_fixed_budget_usd": 100})
        self.assertFalse(result["eligible_for_preview"])
        self.assertIn("Insufficient Connects", result["reasons"])
        self.assertFalse(result["eligible_for_submission"])

    def test_user_confirmation_always_required(self):
        job = {"can_apply": True, "connects_cost": 1, "score": 80, "hourly_rate_max": 20}
        result = apply_gate(job, 10, {"min_hourly_rate_usd": 15, "min_fixed_budget_usd": 100})
        self.assertTrue(result["eligible_for_preview"])
        self.assertTrue(result["requires_user_confirmation"])
        self.assertFalse(result["eligible_for_submission"])

    def test_hourly_rate_below_minimum_is_blocked(self):
        job = {"can_apply": True, "connects_cost": 1, "score": 80, "hourly_rate_max": 12}
        result = apply_gate(job, 10, {"min_hourly_rate_usd": 15})
        self.assertFalse(result["eligible_for_preview"])
        self.assertIn("Hourly rate below configured minimum", result["reasons"])

    def test_fixed_budget_below_minimum_is_blocked(self):
        job = {"can_apply": True, "connects_cost": 1, "score": 80, "fixed_budget": 75}
        result = apply_gate(job, 10, {"min_fixed_budget_usd": 100})
        self.assertFalse(result["eligible_for_preview"])
        self.assertIn("Fixed budget below configured minimum", result["reasons"])


if __name__ == "__main__":
    unittest.main()
