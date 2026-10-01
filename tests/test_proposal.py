import unittest
from agent.proposal import build_proposal, qualification_check, build_screening_drafts


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "relevant_experience": ["Excel automation", "Google Sheets automation"],
            "proof": "Built a 6-in-1 automated Excel toolkit.",
            "language": "English - Basic",
        }

    def test_proposal_uses_profile_facts(self):
        text = build_proposal({"title": "Excel dashboard", "skills": ["Excel"]}, self.profile)
        self.assertIn("6-in-1 automated Excel toolkit", text)
        self.assertNotIn("10 years", text)

    def test_unmet_qualification_is_reported(self):
        job = {"preferred_qualifications": {"english_proficiency": "Fluent", "rising_talent": True}}
        unmet = qualification_check(job, self.profile)
        self.assertIn("English proficiency: Fluent", unmet)
        self.assertIn("Rising Talent", unmet)

    def test_screening_never_invents(self):
        job = {"screening_questions": ["Describe your experience with Apps Script."]}
        drafts = build_screening_drafts(job, self.profile)
        self.assertIn("Excel automation", drafts[0]["answer"])
        self.assertIn("6-in-1 automated Excel toolkit", drafts[0]["answer"])
        self.assertNotIn("10 years", drafts[0]["answer"])


if __name__ == "__main__":
    unittest.main()
