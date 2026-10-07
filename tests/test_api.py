import os
import unittest
from unittest.mock import patch

# Tests must use a dedicated disposable PostgreSQL database, never DATABASE_URL.
url = os.environ.get('TEST_DATABASE_URL')
if not url:
    raise RuntimeError('TEST_DATABASE_URL is required for API tests')
os.environ['DATABASE_URL'] = url
os.environ['COOKIE_SECURE'] = '0'
os.environ['SESSION_SECRET'] = 'test-only-session-secret'
from cryptography.fernet import Fernet
os.environ['INTEGRATION_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
import app


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'A dedicated TEST_DATABASE_URL is required for PostgreSQL integration tests')
class ApiTests(unittest.TestCase):
    def setUp(self):
        with app.db() as c:
            c.execute('TRUNCATE users RESTART IDENTITY CASCADE')
        app.AUTH_ATTEMPTS.clear()
        self.client = app.app.test_client()
        self.csrf = self.client.get('/api/session').json['csrf']

    def mutate(self, path, payload=None, method='POST', client=None):
        return (client or self.client).open(path, method=method, json=payload,
            headers={'X-CSRF-Token': self.csrf})

    def register(self, email='test@example.com'):
        r = self.mutate('/api/auth/register', {'email': email, 'password': 'testpassword123'})
        self.assertEqual(r.status_code, 200)

    def test_manual_account_isolated_and_does_not_grant_api_access(self):
        path = '/api/channels/bionluk/manual-account'
        payload = {'username':'aykutbayram','notes':'2 ilan; satış yok'}
        self.assertEqual(self.mutate(path,payload,method='PUT').status_code,401)
        self.register()
        self.assertEqual(self.mutate(path,payload,method='PUT').status_code,200)
        channel = next(c for c in self.client.get('/api/channels').json['channels'] if c['platform']=='bionluk')
        self.assertEqual(channel['manual_account']['username'],'aykutbayram')
        self.assertFalse(channel['connected'])
        self.assertEqual(channel['state'],'manual')
        self.assertEqual(self.client.get('/api/channel-orders').json['orders'],[])
        self.assertEqual(self.mutate(path,{'username':[]},method='PUT').status_code,400)
        self.assertEqual(self.mutate('/api/channels/gumroad/manual-account',payload,method='PUT').status_code,400)
        other = app.app.test_client()
        self.csrf = other.get('/api/session').json['csrf']
        self.assertEqual(self.mutate('/api/auth/register',{'email':'second@example.com','password':'testpassword123'},client=other).status_code,200)
        channel = next(c for c in other.get('/api/channels').json['channels'] if c['platform']=='bionluk')
        self.assertIsNone(channel['manual_account'])

    def test_auth_and_csrf(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/register', json={}).status_code, 403)
        self.assertEqual(self.mutate('/api/channel-orders/import', {}).status_code, 401)
        self.register()
        self.assertTrue(self.client.get('/api/me').json['authenticated'])
        self.assertEqual(self.mutate('/api/auth/register', {'email': 'test@example.com','password':'testpassword123'}).status_code,409)
        # Match the browser's JSON content type and explicit empty object.
        self.assertEqual(self.mutate('/api/auth/logout', {}).status_code,200)
        self.assertFalse(self.client.get('/api/me').json['authenticated'])
        self.csrf=self.client.get('/api/session').json['csrf']
        self.assertEqual(self.mutate('/api/auth/login',{'email':'test@example.com','password':'testpassword123'}).status_code,200)

    def test_scan_and_proposal(self):
        self.register()
        job={'title':'Google Sheets Automation Dashboard','skills':['Google Sheets','Automation'],
             'hourly_rate_max':35,'payment_verified':True,'proposals_count':8,'can_apply':True,'connects_cost':5}
        r=self.mutate('/api/scan',{'jobs':[job],'connects_balance':10})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['quota']['used'],1)
        jid=self.client.get('/api/jobs').json['jobs'][0]['id']
        proposal=self.mutate('/api/proposals',{'job_id':jid})
        self.assertEqual(proposal.status_code,200)
        pid=proposal.json['id']
        self.assertEqual(self.mutate('/api/proposals/'+str(pid),{'body':'Reviewed proposal','status':'review'},method='PATCH').status_code,200)
        self.assertEqual(self.client.get('/api/proposals').json['proposals'][0]['body'],'Reviewed proposal')
        self.assertEqual(self.mutate('/api/scan',{'jobs':'bad'}).status_code,400)

    def test_all_panel_reads_after_login(self):
        self.register()
        paths = ['/api/dashboard','/api/jobs','/api/proposals','/api/notifications',
                 '/api/settings','/api/channels','/api/channel-orders',
                 '/api/channel-products','/api/profile']
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code,200,response.json)

    @patch('gumroad_oauth.urllib.request.build_opener')
    def test_gumroad_oauth_readonly_and_replay(self, opener):
        import json
        from urllib.parse import urlparse, parse_qs
        self.register()
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.side_effect = [json.dumps({'access_token':'read-only-test-token',
            'scope':'view_profile view_sales'}).encode(),
            json.dumps({'user':{'name':'MexAy Digital'}}).encode(),
            json.dumps({'success':True,'sales':[]}).encode()]
        start = self.mutate('/api/channels/gumroad/oauth/start',
            {'client_id':'test-client-id','client_secret':'test-client-secret'})
        self.assertEqual(start.status_code, 200)
        params = parse_qs(urlparse(start.json['url']).query)
        self.assertEqual(params['scope'], ['view_profile view_sales'])
        self.assertNotIn('test-client-secret', start.data.decode())
        with app.db() as c:
            row = c.execute('SELECT encrypted_config FROM channel_oauth_pending').fetchone()
            self.assertNotIn('test-client-secret', row['encrypted_config'])
        callback = '/oauth/gumroad/callback?state='+params['state'][0]+'&code=test-code'
        self.assertEqual(self.client.get(callback).location, '/?gumroad=connected')
        self.assertEqual(self.client.get(callback).status_code, 400)
        self.assertEqual(opener.return_value.open.call_count, 3)
        self.assertEqual([call.args[0].full_url for call in opener.return_value.open.call_args_list],
            ['https://gumroad.com/oauth/token','https://api.gumroad.com/v2/user','https://api.gumroad.com/v2/sales'])
        hub = self.client.get('/api/channels').json
        self.assertTrue(next(c for c in hub['channels'] if c['platform']=='gumroad')['connected'])

    @patch('gumroad_oauth.urllib.request.build_opener')
    def test_gumroad_oauth_rejects_broad_scopes_and_wrong_state(self, opener):
        import json
        from urllib.parse import urlparse, parse_qs
        self.register()
        start = self.mutate('/api/channels/gumroad/oauth/start',
            {'client_id':'test-client-id','client_secret':'test-client-secret'})
        state = parse_qs(urlparse(start.json['url']).query)['state'][0]
        self.assertEqual(self.client.get('/oauth/gumroad/callback?state=wrong&code=x').status_code,400)
        opener.return_value.open.assert_not_called()
        start = self.mutate('/api/channels/gumroad/oauth/start',
            {'client_id':'test-client-id','client_secret':'test-client-secret'})
        state = parse_qs(urlparse(start.json['url']).query)['state'][0]
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = json.dumps({'access_token':'broad-test-token',
            'scope':'view_profile view_sales edit_products'}).encode()
        failed = self.client.get('/oauth/gumroad/callback?state='+state+'&code=test-code')
        self.assertEqual(failed.status_code,502)
        self.assertNotIn('broad-test-token',failed.data.decode())
        with app.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM channel_connections WHERE platform='gumroad'").fetchone()['n'],0)

    @patch('central.remote_json')
    def test_upwork_sync_updates_existing_job(self, remote):
        self.register()
        remote.return_value={'data':{'marketplaceJobPostingsSearch':{'edges':[
            {'node':{'id':'job-123','title':'Excel dashboard','description':'Build a dashboard','skills':[]}}]}}}
        self.assertEqual(self.mutate('/api/channels/upwork/connect',{'token':'test-readonly-token'}).status_code,200)
        for _ in range(2):
            response=self.mutate('/api/channels/upwork/sync')
            self.assertEqual(response.status_code,200,response.json)
        jobs=self.client.get('/api/jobs').json['jobs']
        self.assertEqual(len(jobs),1)
        with app.db() as c:
            count=c.execute("SELECT COUNT(*) AS n FROM jobs WHERE external_id=%s",('job-123',)).fetchone()['n']
            self.assertEqual(count,1)

    def order(self, **changes):
        row=dict(platform='upwork',external_id='F1',title='Automation',amount='25.00',currency='USD',status='completed')
        row.update(changes)
        return row

    def test_orders_totals_upsert_and_isolation(self):
        self.register()
        for row in [self.order(),self.order(external_id='F2',currency='EUR',amount='10'),self.order(external_id='F3',status='refunded')]:
            self.assertEqual(self.mutate('/api/channel-orders/import',{'orders':[row]}).status_code,200)
        self.mutate('/api/channel-orders/import',{'orders':[self.order(amount='30')]})
        hub=self.client.get('/api/channels').json
        self.assertEqual({r['currency']:r['amount'] for r in hub['totals']},{'EUR':'10.00','USD':'30.00'})
        self.assertEqual(hub['stats']['orders'],3)
        oid=self.client.get('/api/channel-orders').json['orders'][0]['id']
        other=app.app.test_client()
        token=other.get('/api/session').json['csrf']
        other.post('/api/auth/register',json={'email':'other@example.com','password':'testpassword123'},headers={'X-CSRF-Token':token})
        self.assertEqual(other.get('/api/channel-orders').json['orders'],[])
        self.assertEqual(other.patch('/api/channel-orders/'+str(oid),json={'status':'completed'},headers={'X-CSRF-Token':token}).status_code,404)

    def test_manual_channels_orders_export_and_totals(self):
        self.register()
        hub = self.client.get('/api/channels').json
        for platform in ('bionluk', 'payhip'):
            channel = next(c for c in hub['channels'] if c['platform'] == platform)
            self.assertEqual(channel['state'], 'manual')
            self.assertFalse(channel['connected'])
            self.assertEqual(self.mutate('/api/channels/'+platform+'/connect', {'token':'unused'}).status_code, 400)
            row = self.order(platform=platform, external_id='same-id')
            self.assertEqual(self.mutate('/api/channel-orders/import', {'orders':[row]}).status_code, 200)
        self.assertEqual(self.client.get('/api/channel-orders').json['total'], 2)
        self.assertEqual(self.client.get('/api/channels').json['totals'][0]['amount'], '50.00')
        self.mutate('/api/channel-orders/import', {'orders':[self.order(platform='payhip',external_id='same-id',amount='30')]})
        rows = self.client.get('/api/channel-orders').json['orders']
        self.assertEqual(len(rows), 2)
        oid = next(r['id'] for r in rows if r['platform'] == 'bionluk')
        self.assertEqual(self.mutate('/api/channel-orders/'+str(oid), {'status':'refunded'}, method='PATCH').status_code, 200)
        self.assertEqual(self.client.get('/api/channels').json['totals'][0]['amount'], '30.00')
        exported = self.client.get('/api/channel-orders/export').data.decode()
        self.assertIn('bionluk,same-id', exported)
        self.assertIn('payhip,same-id', exported)

    def test_import_validation_atomic_and_csv_safety(self):
        self.register()
        for amount in ['NaN','Infinity','-1','0.001']:
            self.assertEqual(self.mutate('/api/channel-orders/import',{'orders':[self.order(amount=amount)]}).status_code,400)
        self.assertEqual(self.mutate('/api/channel-orders/import',{'orders':[self.order(),self.order(platform='bad')]}).status_code,400)
        self.assertEqual(self.client.get('/api/channel-orders').json['total'],0)
        self.mutate('/api/channel-orders/import',{'orders':[self.order(title='=HYPERLINK("x")')]})
        self.assertIn("'=HYPERLINK",self.client.get('/api/channel-orders/export').data.decode())

    @patch('central.remote_json')
    def test_gumroad_encrypted_sync_dedup_and_failure(self,remote):
        self.register()
        token='not-a-real-provider-token'
        def provider(platform, key, path=None, params=None):
            self.assertEqual(key,token)
            if path=='user': return {'user':{'name':'MexAy'}}
            if path=='products': return {'products':[{'id':'P1','name':'Toolkit','price':2500,'currency':'usd','published':True}]}
            return {'sales':[{'id':'S1','price':2500,'product_name':'Toolkit','created_at':'2026-10-01T00:00:00Z'}, {'id':'TEST','price':2500,'is_test_purchase':True,'created_at':'2026-10-01T00:00:00Z'}]}
        remote.side_effect=provider
        self.assertEqual(self.mutate('/api/channels/gumroad/connect',{'token':token}).status_code,200)
        with app.db() as c:
            stored=c.execute('SELECT encrypted_token FROM channel_connections').fetchone()['encrypted_token']
        self.assertNotIn(token,stored)
        self.assertNotIn(token,str(self.client.get('/api/channels').json))
        for _ in range(2): self.assertEqual(self.mutate('/api/channels/gumroad/sync').status_code,200)
        self.assertEqual(self.client.get('/api/channel-orders').json['total'],2)
        self.assertEqual(self.client.get('/api/channels').json['totals'][0]['amount'],'25.00')
        oid=self.client.get('/api/channel-orders').json['orders'][0]['id']
        self.assertEqual(self.mutate('/api/channel-orders/'+str(oid),{'status':'cancelled'},method='PATCH').status_code,409)
        from central import ProviderError
        remote.side_effect=ProviderError('unavailable')
        self.assertEqual(self.mutate('/api/channels/gumroad/sync').status_code,502)
        self.assertEqual(self.client.get('/api/channel-orders').json['total'],2)
        self.assertEqual(self.client.get('/api/channels').json['channels'][1]['state'],'attention')

    def test_google_state_rejected_and_fiverr_manual(self):
        self.assertIn('google_state',self.client.get('/auth/google/callback?code=bad&state=bad').location)
        self.register()
        self.assertEqual(self.mutate('/api/channels/fiverr/connect',{'token':'not-real-token'}).status_code,400)
        self.assertEqual(self.mutate('/api/channels/gumroad/sync').status_code,409)

    def secure_call(self,method,client,path,**kwargs):
        headers=kwargs.pop('headers',{})
        headers['X-CSRF-Token']=client.get('/api/session').json['csrf']
        return client.open(path,method=method,headers=headers,**kwargs)

    def test_profile_settings_proposals_and_tenant_isolation(self):
        self.secure_call('POST',self.client,'/api/auth/register', json={'email':'one@example.com','password':'longpassword123'})
        self.assertEqual(self.secure_call('PUT',self.client,'/api/profile', json={'relevant_experience':['Personal CRM prototype'], 'proof':'Self-initiated portfolio example.'}).status_code, 200)
        self.assertEqual(self.secure_call('PUT',self.client,'/api/settings', json={'min_hourly':80,'min_fixed':100,'keywords':['excel'],'excludes':['gambling']}).status_code, 200)
        job={'title':'Excel dashboard', 'hourly_rate_max':30,'connects_cost':1,'can_apply':True}
        result=self.secure_call('POST',self.client,'/api/scan', json={'jobs':[job], 'connects_balance':10})
        self.assertEqual(result.status_code,200)
        self.assertIn('Hourly rate below configured minimum',result.get_json()['result'][0]['eligibility']['reasons'])
        jid=self.client.get('/api/jobs').get_json()['jobs'][0]['id']
        proposal=self.secure_call('POST',self.client,'/api/proposals', json={'job_id':jid})
        self.assertEqual(proposal.status_code,200)
        self.assertIn('Personal CRM prototype',proposal.get_json()['body'])
        pid=proposal.get_json()['id']
        self.assertEqual(self.secure_call('PATCH',self.client,f'/api/proposals/{pid}', json={'body':'Reviewed draft','status':'review'}).status_code,200)
        self.assertEqual(self.client.get('/api/proposals').get_json()['proposals'][0]['body'],'Reviewed draft')
        other=app.app.test_client()
        self.secure_call('POST',other,'/api/auth/register', json={'email':'two@example.com','password':'longpassword123'})
        self.assertEqual(other.get('/api/jobs').get_json()['jobs'],[])
        self.assertEqual(self.secure_call('PATCH',other,f'/api/proposals/{pid}', json={'status':'approved'}).status_code,404)

    def test_recovery_token_is_single_use_and_revokes_sessions(self):
        import hashlib,datetime
        self.secure_call('POST',self.client,'/api/auth/register', json={'email':'reset@example.com','password':'longpassword123'})
        second=app.app.test_client()
        self.secure_call('POST',second,'/api/auth/login',json={'email':'reset@example.com','password':'longpassword123'})
        with patch.object(app.mailer,'configured',return_value=True), patch.object(app.mailer,'send',return_value=True) as send:
            self.assertEqual(self.secure_call('POST',self.client,'/api/auth/forgot',json={'email':'reset@example.com'}).status_code,200)
            from urllib.parse import urlparse,parse_qs
            url=send.call_args.args[2].splitlines()[1]
            token=parse_qs(urlparse(url).query)['token'][0]
        payload={'token':token,'password':'newlongpassword123'}
        self.assertEqual(self.secure_call('POST',self.client,'/api/auth/reset-password',json=payload).status_code,200)
        self.assertEqual(second.get('/api/jobs').status_code,401)
        self.assertEqual(self.secure_call('POST',self.client,'/api/auth/reset-password',json=payload).status_code,400)
        self.assertEqual(self.secure_call('POST',self.client,'/api/auth/login',json={'email':'reset@example.com','password':'longpassword123'}).status_code,401)
        self.assertEqual(self.secure_call('POST',self.client,'/api/auth/login',json={'email':'reset@example.com','password':'newlongpassword123'}).status_code,200)

    def test_google_state_and_bad_requests(self):
        self.assertEqual(self.secure_call('POST',self.client,'/api/auth/register',json=[]).status_code,400)
        self.assertEqual(self.secure_call('POST',self.client,'/api/auth/login',json={'email':'a@example.com','password':'longpassword123'},headers={'Origin':'https://evil.example'}).status_code,403)
        with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret','GOOGLE_REDIRECT_URI':'https://example.com/auth/google/callback'}):
            self.assertEqual(self.client.get('/auth/google').status_code,302)
            response=self.client.get('/auth/google/callback?code=unused&state=wrong')
            self.assertIn('google_state',response.location)

    def test_missing_profile_file_does_not_break_pipeline(self):
        from agent.pipeline import run_pipeline
        results=run_pipeline([{'title':'Excel dashboard'}])
        self.assertEqual(len(results),1)
        self.assertNotIn('Verified experience #1',results[0]['proposal_preview'])

    def test_business_schema_isolation_and_restart(self):
        with app.db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS public.users(
                id BIGSERIAL PRIMARY KEY,business_id BIGINT,email TEXT,password_hash TEXT,
                role TEXT,permissions TEXT,created_at TIMESTAMPTZ,email_verified_at TIMESTAMPTZ)""")
            c.execute("""CREATE TABLE IF NOT EXISTS public.password_reset_tokens(
                token_hash TEXT PRIMARY KEY,user_id BIGINT,expires_at TIMESTAMPTZ,
                used_at TIMESTAMPTZ,created_at TIMESTAMPTZ)""")
            columns=c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='users'").fetchall()
            self.assertNotIn('usage_period',[r['column_name'] for r in columns])
        app.init_db()
        self.register('isolated@example.com')
        self.assertTrue(self.client.get('/api/me').json['authenticated'])
        self.assertEqual(self.client.get('/health').json['schema'],'upwork_agent')
        app.init_db()
        self.assertTrue(self.client.get('/api/me').json['authenticated'])
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM public.users').fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n'],1)
