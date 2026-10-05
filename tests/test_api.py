import os
import tempfile
import unittest
from unittest.mock import patch

if os.environ.get('TEST_DATABASE_URL'):
    os.environ['DATABASE_URL'] = os.environ['TEST_DATABASE_URL']
    import app


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'A dedicated TEST_DATABASE_URL is required for PostgreSQL integration tests')
class ApiTests(unittest.TestCase):
    def setUp(self):
        app.init_db()
        with app.db() as c:
            c.execute('TRUNCATE users RESTART IDENTITY CASCADE')
        app.AUTH_ATTEMPTS.clear()
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def tearDown(self):
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

    def test_health_and_auth_guards(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "ok")

        r = self.client.post("/api/scan", json={"jobs": []})
        self.assertEqual(r.status_code, 401)

        r = self.client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrongpass"})
        self.assertEqual(r.status_code, 401)

    def test_duplicate_registration_and_logout(self):
        payload = {"email": "duplicate@example.com", "password": "testpassword123"}
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 409)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertFalse(self.client.get("/api/me").get_json()["authenticated"])

    def test_invalid_json_payloads_are_rejected(self):
        r = self.client.post("/api/auth/register", json={"email": 123, "password": "testpassword123"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/login", json={"email": "x@example.com", "password": 123})
        self.assertEqual(r.status_code, 400)

    def test_invalid_jobs_payload_is_rejected(self):
        self.client.post("/api/auth/register", json={
            "email": "invalid@example.com",
            "password": "testpassword123",
        })
        r = self.client.post("/api/scan", json={"jobs": "not-a-list"})
        self.assertEqual(r.status_code, 400)

    def test_profile_settings_proposals_and_tenant_isolation(self):
        self.client.post('/api/auth/register', json={'email':'one@example.com','password':'longpassword123'})
        self.assertEqual(self.client.put('/api/profile', json={'relevant_experience':['Personal CRM prototype'], 'proof':'Self-initiated portfolio example.'}).status_code, 200)
        self.assertEqual(self.client.put('/api/settings', json={'min_hourly':80,'min_fixed':100,'keywords':['excel'],'excludes':['gambling']}).status_code, 200)
        job={'title':'Excel dashboard', 'hourly_rate_max':30,'connects_cost':1,'can_apply':True}
        result=self.client.post('/api/scan', json={'jobs':[job], 'connects_balance':10})
        self.assertEqual(result.status_code,200)
        self.assertIn('Hourly rate below configured minimum',result.get_json()['result'][0]['eligibility']['reasons'])
        jid=self.client.get('/api/jobs').get_json()['jobs'][0]['id']
        proposal=self.client.post('/api/proposals', json={'job_id':jid})
        self.assertEqual(proposal.status_code,200)
        self.assertIn('Personal CRM prototype',proposal.get_json()['body'])
        pid=proposal.get_json()['id']
        self.assertEqual(self.client.patch(f'/api/proposals/{pid}', json={'body':'Reviewed draft','status':'review'}).status_code,200)
        self.assertEqual(self.client.get('/api/proposals').get_json()['proposals'][0]['body'],'Reviewed draft')
        other=app.app.test_client()
        other.post('/api/auth/register', json={'email':'two@example.com','password':'longpassword123'})
        self.assertEqual(other.get('/api/jobs').get_json()['jobs'],[])
        self.assertEqual(other.patch(f'/api/proposals/{pid}', json={'status':'approved'}).status_code,404)

    def test_recovery_token_is_single_use_and_revokes_sessions(self):
        import hashlib,datetime
        self.client.post('/api/auth/register', json={'email':'reset@example.com','password':'longpassword123'})
        second=app.app.test_client()
        second.post('/api/auth/login',json={'email':'reset@example.com','password':'longpassword123'})
        with patch.object(app.mailer,'configured',return_value=True), patch.object(app.mailer,'send',return_value=True) as send:
            self.assertEqual(self.client.post('/api/auth/forgot',json={'email':'reset@example.com'}).status_code,200)
            from urllib.parse import urlparse,parse_qs
            url=send.call_args.args[2].splitlines()[1]
            token=parse_qs(urlparse(url).query)['token'][0]
        payload={'token':token,'password':'newlongpassword123'}
        self.assertEqual(self.client.post('/api/auth/reset-password',json=payload).status_code,200)
        self.assertEqual(second.get('/api/jobs').status_code,401)
        self.assertEqual(self.client.post('/api/auth/reset-password',json=payload).status_code,400)
        self.assertEqual(self.client.post('/api/auth/login',json={'email':'reset@example.com','password':'longpassword123'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'email':'reset@example.com','password':'newlongpassword123'}).status_code,200)

    def test_google_state_and_bad_requests(self):
        self.assertEqual(self.client.post('/api/auth/register',json=[]).status_code,400)
        self.assertEqual(self.client.post('/api/auth/login',json={'email':'a@example.com','password':'longpassword123'},headers={'Origin':'https://evil.example'}).status_code,403)
        with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret','GOOGLE_REDIRECT_URI':'https://example.com/auth/google/callback'}):
            self.assertEqual(self.client.get('/auth/google').status_code,302)
            response=self.client.get('/auth/google/callback?code=unused&state=wrong')
            self.assertIn('google_state',response.location)

    def test_missing_profile_file_does_not_break_pipeline(self):
        from agent.pipeline import run_pipeline
        results=run_pipeline([{'title':'Excel dashboard'}])
        self.assertEqual(len(results),1)
        self.assertNotIn('Verified experience #1',results[0]['proposal_preview'])


if __name__ == "__main__":
    unittest.main()
