"""Read-only Gmail notification feed for the freelance workspace."""
import datetime
import html
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
from email.utils import parseaddr

from cryptography.fernet import InvalidToken
from flask import Blueprint, jsonify, redirect, request, session
from central import cipher, NoRedirect, ProviderError

SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
QUERY = 'from:(fiverr.com) -in:spam -in:trash newer_than:90d'


def configured():
    return all(os.getenv(k) for k in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                                      'GMAIL_REDIRECT_URI', 'INTEGRATION_ENCRYPTION_KEY'))


def google_json(path, token=None, form=None, params=None):
    if form is not None:
        url = 'https://oauth2.googleapis.com/token'
        data = urllib.parse.urlencode(form).encode()
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    else:
        if not re.fullmatch(r'(profile|messages|messages/[A-Za-z0-9_-]+)', path):
            raise ProviderError('Geçersiz Gmail isteği.')
        url = 'https://gmail.googleapis.com/gmail/v1/users/me/' + path
        if params:
            url += '?' + urllib.parse.urlencode(params, doseq=True)
        data = None
        headers = {'Authorization': 'Bearer ' + token}
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=4) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get('error'):
            raise ValueError()
        return result
    except Exception:
        raise ProviderError('Gmail erişimi başarısız. Bağlantıyı ve Google izinlerini kontrol edin.') from None


def token_form(**extra):
    return dict(client_id=os.environ['GOOGLE_CLIENT_ID'],
                client_secret=os.environ['GOOGLE_CLIENT_SECRET'], **extra)


def parse_notification(message):
    headers = {str(h.get('name', '')).lower(): str(h.get('value', ''))
               for h in message.get('payload', {}).get('headers', [])}
    sender = parseaddr(headers.get('from', ''))[1].lower()
    domain = sender.rpartition('@')[2]
    if not sender or not (domain == 'fiverr.com' or domain.endswith('.fiverr.com')):
        return None
    mid = str(message.get('id', ''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', mid):
        return None
    subject = headers.get('subject', '').strip()[:300] or 'Fiverr bildirimi'
    # Classify by subject only: quoted message text must not turn a message into an order.
    text = subject.casefold()
    kind = 'notification'
    for category, pattern in (
        ('message', r'new message|sent you a message|yeni mesaj|mesaj gönder'),
        ('offer', r'custom offer|new offer|özel teklif|yeni teklif'),
        ('order', r'\border\b|\bdelivery\b|\brevision\b|sipariş|teslimat|revizyon'),
    ):
        if re.search(pattern, text):
            kind = category
            break
    try:
        occurred = datetime.datetime.fromtimestamp(int(message['internalDate']) / 1000,
                                                   datetime.timezone.utc)
    except (KeyError, ValueError, TypeError, OverflowError, OSError):
        return None
    return dict(external_id=mid, category=kind, subject=subject, sender=sender[:254],
                preview=html.unescape(str(message.get('snippet', '')))[:1000],
                occurred_at=occurred, unread='UNREAD' in message.get('labelIds', []))


def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS channel_mail_events (
        id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        platform TEXT NOT NULL DEFAULT 'fiverr', external_id TEXT NOT NULL,
        category TEXT NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,
        preview TEXT NOT NULL DEFAULT '', occurred_at TIMESTAMPTZ NOT NULL,
        unread BOOLEAN NOT NULL DEFAULT FALSE, UNIQUE(user_id, platform, external_id))''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_mail_user_date ON channel_mail_events(user_id, occurred_at DESC)')


def register(app, db, auth_required):
    bp = Blueprint('fiverr_mail', __name__)

    @bp.errorhandler(ProviderError)
    def provider_error(error):
        return jsonify(error=str(error)), 502

    @bp.get('/api/fiverr-mail')
    def feed():
        if (e := auth_required()): return e
        with db() as c:
            con = c.execute("SELECT label,last_synced_at,last_error FROM channel_connections WHERE user_id=%s AND platform='fiverr'", (session['user_id'],)).fetchone()
            events = c.execute('SELECT * FROM channel_mail_events WHERE user_id=%s ORDER BY occurred_at DESC LIMIT 200', (session['user_id'],)).fetchall()
        return jsonify(ready=configured(), connected=bool(con), connection=con, events=events)

    @bp.post('/api/fiverr-mail/connect')
    def connect():
        if (e := auth_required()): return e
        if not configured():
            return jsonify(error='Sunucuda Gmail OAuth yapılandırması henüz tamamlanmadı.'), 503
        cipher()  # Validate the encryption key before leaving the app.
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        import base64, hashlib
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        session['fiverr_gmail_oauth'] = dict(state=state, verifier=verifier, created=time.time(), uid=session['user_id'])
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(dict(
            client_id=os.environ['GOOGLE_CLIENT_ID'], redirect_uri=os.environ['GMAIL_REDIRECT_URI'],
            response_type='code', scope=SCOPE, access_type='offline', prompt='consent select_account',
            state=state, code_challenge=challenge, code_challenge_method='S256'))
        return jsonify(url=url)

    @bp.get('/auth/gmail/callback')
    def callback():
        if (e := auth_required()): return e
        flow = session.pop('fiverr_gmail_oauth', {})
        state = request.args.get('state', '')
        if (not flow or not state or not secrets.compare_digest(flow.get('state', ''), state)
                or flow.get('uid') != session['user_id'] or time.time() - flow.get('created', 0) > 600):
            return redirect('/?gmail_result=invalid_state')
        if request.args.get('error') or not request.args.get('code'):
            return redirect('/?gmail_result=cancelled')
        try:
            tokens = google_json('', form=token_form(code=request.args['code'],
                grant_type='authorization_code', redirect_uri=os.environ['GMAIL_REDIRECT_URI'],
                code_verifier=flow['verifier']))
            if SCOPE not in str(tokens.get('scope', '')).split() or not tokens.get('refresh_token'):
                raise ProviderError('Gmail okuma ve çevrimdışı erişim izni gerekli.')
            profile = google_json('profile', token=tokens['access_token'])
            tokens['expires_at'] = time.time() + int(tokens.get('expires_in', 3600))
            encrypted = cipher().encrypt(json.dumps(tokens).encode()).decode()
            with db() as c:
                # Replace account atomically and remove the old mailbox feed.
                c.execute('SELECT pg_advisory_xact_lock(%s)', (session['user_id'],))
                c.execute('DELETE FROM channel_mail_events WHERE user_id=%s', (session['user_id'],))
                c.execute("""INSERT INTO channel_connections(user_id,platform,encrypted_token,label)
                    VALUES(%s,'fiverr',%s,%s) ON CONFLICT(user_id,platform) DO UPDATE SET
                    encrypted_token=EXCLUDED.encrypted_token,label=EXCLUDED.label,
                    cursor='',last_synced_at=NULL,last_error=''""", (session['user_id'], encrypted, str(profile['emailAddress'])[:254]))
        except (ProviderError, KeyError, ValueError, TypeError):
            return redirect('/?gmail_result=failed')
        return redirect('/?gmail_result=connected')

    @bp.delete('/api/fiverr-mail/connection')
    def disconnect():
        if (e := auth_required()): return e
        with db() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)', (session['user_id'],))
            c.execute("DELETE FROM channel_connections WHERE user_id=%s AND platform='fiverr'", (session['user_id'],))
            c.execute('DELETE FROM channel_mail_events WHERE user_id=%s', (session['user_id'],))
        session.pop('fiverr_gmail_oauth', None)
        return jsonify(ok=True)

    @bp.post('/api/fiverr-mail/sync')
    def sync():
        if (e := auth_required()): return e
        uid = session['user_id']
        with db() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)', (uid,))
            con = c.execute("SELECT * FROM channel_connections WHERE user_id=%s AND platform='fiverr' FOR UPDATE", (uid,)).fetchone()
            if not con:
                return jsonify(error='Önce Gmail hesabınızı MexAy üzerinden bağlayın.'), 409
            # Limit polling across tabs; a queued request observes the updated timestamp.
            if con['last_synced_at'] and (datetime.datetime.now(datetime.timezone.utc) - con['last_synced_at']).total_seconds() < 60:
                return jsonify(ok=True, processed=0, has_more=bool(con['cursor']), throttled=True)
            try:
                tokens = json.loads(cipher().decrypt(con['encrypted_token'].encode()))
                if time.time() >= float(tokens.get('expires_at', 0)) - 60:
                    fresh = google_json('', form=token_form(grant_type='refresh_token', refresh_token=tokens['refresh_token']))
                    tokens.update(fresh)
                    tokens['expires_at'] = time.time() + int(fresh.get('expires_in', 3600))
                params = dict(q=QUERY, maxResults=3)
                if con['cursor']: params['pageToken'] = con['cursor']
                listing = google_json('messages', token=tokens['access_token'], params=params)
                count = 0
                for item in listing.get('messages', []):
                    mid = str(item['id'])
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', mid): raise ValueError()
                    message = google_json('messages/' + mid, token=tokens['access_token'],
                        params={'format':'metadata', 'metadataHeaders':['From','Subject']})
                    event = parse_notification(message)
                    if event is None: continue
                    c.execute('''INSERT INTO channel_mail_events(user_id,external_id,category,subject,sender,preview,occurred_at,unread)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,platform,external_id)
                        DO UPDATE SET unread=EXCLUDED.unread,preview=EXCLUDED.preview''',
                        (uid,event['external_id'],event['category'],event['subject'],event['sender'],event['preview'],event['occurred_at'],event['unread']))
                    count += 1
                cursor = str(listing.get('nextPageToken') or '')
                c.execute("""UPDATE channel_connections SET encrypted_token=%s,cursor=%s,last_synced_at=NOW(),last_error=''
                    WHERE user_id=%s AND platform='fiverr'""", (cipher().encrypt(json.dumps(tokens).encode()).decode(),cursor,uid))
            except (ProviderError, InvalidToken, ValueError, KeyError, TypeError):
                c.rollback()
                c.execute("UPDATE channel_connections SET last_error=%s WHERE user_id=%s AND platform='fiverr'", ('Gmail eşitlemesi başarısız. İzinleri kontrol edin veya yeniden bağlayın.',uid))
                return jsonify(error='Gmail eşitlemesi başarısız. İzinleri kontrol edin veya yeniden bağlayın.'), 502
        return jsonify(ok=True, processed=count, has_more=bool(cursor))

    app.register_blueprint(bp)
