import datetime
import os
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask, session, jsonify
from cryptography.fernet import Fernet
import fiverr_mail as mail


class MailTests(unittest.TestCase):
    def message(self, subject='You have a new message', sender='Fiverr <notify@e.fiverr.com>'):
        return dict(id='abc123', internalDate='1791244800000', snippet='Hello &amp; welcome',
                    labelIds=['UNREAD'], payload={'headers':[
                        {'name':'From','value':sender},{'name':'Subject','value':subject}]})

    def test_categories(self):
        for title, category in [('You have a new message','message'),
                                ('Your order is ready','order'),('New custom offer','offer'),
                                ('Welcome to Fiverr','notification'),
                                ('You have a new message about an order','message')]:
            self.assertEqual(mail.parse_notification(self.message(title))['category'], category)

    def test_reject_lookalike_and_google_login_mail(self):
        for sender in ['fiverr@google.com','x@fiverr.com.evil.test','Fiverr <x@evil.test>', 'x@notfiverr.com']:
            self.assertIsNone(mail.parse_notification(self.message(sender=sender)))

    def test_malformed_message_and_preview(self):
        m=self.message(); m['id']='../../profile'
        self.assertIsNone(mail.parse_notification(m))
        m=self.message(); m['internalDate']='oops'
        self.assertIsNone(mail.parse_notification(m))
        self.assertEqual(mail.parse_notification(self.message())['preview'],'Hello & welcome')

    def setUp(self):
        self.env=patch.dict(os.environ, {'GOOGLE_CLIENT_ID':'test-client',
            'GOOGLE_CLIENT_SECRET':'test-secret','GMAIL_REDIRECT_URI':'https://mexay.example/auth/gmail/callback',
            'INTEGRATION_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start(); self.addCleanup(self.env.stop)
        self.app=Flask(__name__); self.app.secret_key='test-secret'
        self.db=MagicMock(); self.c=self.db.return_value.__enter__.return_value
        def auth():
            if not session.get('user_id'): return jsonify(error='login required'),401
        mail.register(self.app,self.db,auth)
        self.client=self.app.test_client()

    def login(self, uid=17):
        with self.client.session_transaction() as s: s['user_id']=uid

    def test_requires_login(self):
        for path, method in [('/api/fiverr-mail','GET'),('/api/fiverr-mail/connect','POST'),
                             ('/api/fiverr-mail/sync','POST'),('/api/fiverr-mail/connection','DELETE')]:
            self.assertEqual(self.client.open(path,method=method).status_code,401)
        self.db.assert_not_called()

    def test_oauth_scoped_offline_pkce(self):
        self.login()
        from urllib.parse import urlparse,parse_qs
        r=self.client.post('/api/fiverr-mail/connect')
        params=parse_qs(urlparse(r.json['url']).query)
        self.assertEqual(params['scope'],[mail.SCOPE])
        self.assertEqual(params['access_type'],['offline'])
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertNotIn('test-secret',r.json['url'])

    def test_missing_config(self):
        self.login()
        with patch.dict(os.environ,{'GMAIL_REDIRECT_URI':''}):
            self.assertEqual(self.client.post('/api/fiverr-mail/connect').status_code,503)

    def test_callback_rejects_state_and_cross_user(self):
        self.login(); self.client.post('/api/fiverr-mail/connect')
        with self.client.session_transaction() as s:
            state=s['fiverr_gmail_oauth']['state'];s['user_id']=18
        with patch.object(mail,'google_json') as remote:
            self.assertIn('invalid_state',self.client.get('/auth/gmail/callback?state='+state+'&code=test').location)
            remote.assert_not_called()
        self.db.assert_not_called()

    def test_callback_expiry_and_cancel(self):
        self.login();self.client.post('/api/fiverr-mail/connect')
        with self.client.session_transaction() as s:
            f=s['fiverr_gmail_oauth'];state=f['state'];f['created']=0;s['fiverr_gmail_oauth']=f
        self.assertIn('invalid_state',self.client.get('/auth/gmail/callback?state='+state+'&code=test').location)
        self.client.post('/api/fiverr-mail/connect')
        with self.client.session_transaction() as s: state=s['fiverr_gmail_oauth']['state']
        self.assertIn('cancelled',self.client.get('/auth/gmail/callback?state='+state+'&error=access_denied').location)

    def test_callback_encrypts_tokens_and_clears_old_feed(self):
        self.login();self.client.post('/api/fiverr-mail/connect')
        with self.client.session_transaction() as s: state=s['fiverr_gmail_oauth']['state']
        with patch.object(mail,'google_json',side_effect=[{'access_token':'secret-access','refresh_token':'secret-refresh','scope':mail.SCOPE},{'emailAddress':'owner@example.com'}]):
            r=self.client.get('/auth/gmail/callback?state='+state+'&code=test')
        self.assertIn('connected',r.location)
        calls=self.c.execute.call_args_list
        self.assertTrue(any('DELETE FROM channel_mail_events' in call.args[0] for call in calls))
        encrypted=calls[-1].args[1][1]
        self.assertNotIn('secret-refresh',encrypted)
        self.assertIn('secret-refresh',mail.cipher().decrypt(encrypted.encode()).decode())

    def test_callback_missing_scope_or_refresh_token(self):
        self.login()
        for token in [{'access_token':'x','scope':mail.SCOPE},{'access_token':'x','refresh_token':'y','scope':'openid'}]:
            self.client.post('/api/fiverr-mail/connect')
            with self.client.session_transaction() as s: state=s['fiverr_gmail_oauth']['state']
            with patch.object(mail,'google_json',return_value=token):
                self.assertIn('failed',self.client.get('/auth/gmail/callback?state='+state+'&code=test').location)
        self.db.assert_not_called()

    def test_sync_refresh_and_deduplicate(self):
        self.login()
        import json
        self.c.execute.return_value.fetchone.return_value=dict(encrypted_token=mail.cipher().encrypt(json.dumps({'access_token':'old','refresh_token':'refresh','expires_at':0}).encode()).decode(),cursor='',last_synced_at=None)
        with patch.object(mail,'google_json',side_effect=[{'access_token':'new','expires_in':3600},{'messages':[{'id':'abc123'}],'nextPageToken':'next'},self.message()]) as remote:
            r=self.client.post('/api/fiverr-mail/sync')
        self.assertEqual(r.status_code,200);self.assertTrue(r.json['has_more'])
        self.assertEqual(remote.call_args_list[1].kwargs['params']['q'],mail.QUERY)
        sql=' '.join(call.args[0] for call in self.c.execute.call_args_list)
        self.assertIn('ON CONFLICT',sql)
        self.assertNotIn('INSERT INTO channel_orders',sql)

    def test_sync_failure_redacts_and_rolls_back(self):
        self.login()
        self.c.execute.return_value.fetchone.return_value=dict(encrypted_token='broken',cursor='',last_synced_at=None)
        r=self.client.post('/api/fiverr-mail/sync')
        self.assertEqual(r.status_code,502);self.c.rollback.assert_called_once()
        self.assertNotIn('broken',str(r.json))

    def test_poll_throttle_and_disconnect_isolation(self):
        self.login()
        self.c.execute.return_value.fetchone.return_value={'last_synced_at':datetime.datetime.now(datetime.timezone.utc),'cursor':''}
        with patch.object(mail,'google_json') as remote:
            self.assertTrue(self.client.post('/api/fiverr-mail/sync').json['throttled']);remote.assert_not_called()
        self.client.delete('/api/fiverr-mail/connection')
        for call in self.c.execute.call_args_list:
            if 'DELETE' in call.args[0]: self.assertEqual(call.args[1],(17,))

    def test_remote_endpoint_allowlist(self):
        with self.assertRaises(mail.ProviderError): mail.google_json('../../other',token='secret')

if __name__=='__main__': unittest.main()
