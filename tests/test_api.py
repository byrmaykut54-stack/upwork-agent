import os
import tempfile
import unittest

import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        app.DB = self.tmp.name
        app.init_db()
        self.client = app.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except FileNotFoundError:
            pass

    def test_register_login_me_and_scan(self):
        email = "test@example.com"
        password = "testpassword123"

        r = self.client.post("/api/auth/register", json={"email": email, "password": password})
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/me")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["authenticated"])

        job = {
            "title": "Google Sheets Automation Dashboard",
            "skills": ["Google Sheets", "Automation"],
            "hourly_rate_max": 35,
            "payment_verified": True,
            "proposals": 8,
            "proposals_count": 8,
            "can_apply": True,
            "connects_cost": 5,
        }
        r = self.client.post("/api/scan", json={"jobs": [job], "connects_balance": 10})
        self.assertEqual(r.status_code, 200)
        self.assertIn("result", r.get_json())
        self.assertEqual(r.get_json()["quota"]["used"], 1)

    def test_invalid_jobs_payload_is_rejected(self):
        self.client.post("/api/auth/register", json={
            "email": "invalid@example.com",
            "password": "testpassword123",
        })
        r = self.client.post("/api/scan", json={"jobs": "not-a-list"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
