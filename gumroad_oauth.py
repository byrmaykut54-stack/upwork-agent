"""Read-only Gumroad OAuth; credentials remain encrypted and server-side."""
import json
import os
import secrets
import urllib.parse
import urllib.request

from flask import jsonify, request, session, redirect

SCOPES = {"view_profile", "view_sales"}


def callback_uri():
    base = os.environ.get("APP_BASE_URL", "https://upwork-agent-pro.onrender.com").rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("OAuth için HTTPS uygulama adresi gerekli.")
    return base + "/oauth/gumroad/callback"


def register_oauth(bp, db, auth_required, cipher, remote_json, no_redirect, provider_error):
    @bp.post("/api/channels/gumroad/oauth/start")
    def start():
        if (error := auth_required()):
            return error
        data = request.get_json(silent=True) or {}
        client_id, secret = data.get("client_id"), data.get("client_secret")
        if not all(isinstance(v, str) and 10 <= len(v) <= 256 and not any(c.isspace() for c in v)
                   for v in (client_id, secret)):
            return jsonify(error="Geçerli uygulama kimliği ve uygulama anahtarı gerekli."), 400
        state = secrets.token_urlsafe(32)
        uri = callback_uri()
        config = cipher().encrypt(json.dumps({"client_id": client_id, "client_secret": secret,
                                              "redirect_uri": uri}).encode()).decode()
        with db() as c:
            c.execute("DELETE FROM channel_oauth_pending WHERE expires_at < NOW() OR user_id=%s", (session["user_id"],))
            c.execute("INSERT INTO channel_oauth_pending VALUES(%s,%s,%s,NOW()+INTERVAL '10 minutes')",
                      (state, session["user_id"], config))
        session["gumroad_oauth_state"] = state
        params = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": uri,
                                        "scope": "view_profile view_sales", "state": state,
                                        "response_type": "code"})
        return jsonify(url="https://gumroad.com/oauth/authorize?" + params)

    @bp.get("/oauth/gumroad/callback")
    def callback():
        if (error := auth_required()):
            return error
        expected = session.pop("gumroad_oauth_state", "")
        supplied = request.args.get("state", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            return jsonify(error="Bağlantı oturumu geçersiz. Panelden yeniden başlatın."), 400
        with db() as c:
            pending = c.execute("""DELETE FROM channel_oauth_pending
                WHERE state=%s AND user_id=%s RETURNING encrypted_config, expires_at > NOW() AS valid""",
                (expected, session["user_id"])).fetchone()
        if not pending or not pending["valid"]:
            return jsonify(error="Bağlantı oturumunun süresi doldu. Panelden yeniden başlatın."), 400
        if request.args.get("error"):
            return redirect("/?gumroad=cancelled")
        code = request.args.get("code", "")
        if not code or len(code) > 2048:
            return jsonify(error="Gumroad yetkilendirme kodu gelmedi."), 400
        try:
            config = json.loads(cipher().decrypt(pending["encrypted_config"].encode()))
            body = urllib.parse.urlencode(dict(config, code=code, grant_type="authorization_code")).encode()
            req = urllib.request.Request("https://gumroad.com/oauth/token", data=body,
                                         headers={"Accept": "application/json"})
            with urllib.request.build_opener(no_redirect()).open(req, timeout=12) as response:
                raw = response.read(16_385)
            if len(raw) > 16_384:
                raise ValueError()
            result = json.loads(raw)
            granted = set(str(result.get("scope", "")).split())
            token = result.get("access_token")
            if granted != SCOPES or not isinstance(token, str) or not 10 <= len(token) <= 4096:
                raise ValueError()
            profile = remote_json("gumroad", token, "user")
            remote_json("gumroad", token, "sales")
            encrypted = cipher().encrypt(token.encode()).decode()
            label = str(profile.get("user", {}).get("name", "Gumroad"))[:200]
            with db() as c:
                c.execute("""INSERT INTO channel_connections(user_id,platform,encrypted_token,label)
                    VALUES(%s,'gumroad',%s,%s) ON CONFLICT(user_id,platform) DO UPDATE
                    SET encrypted_token=EXCLUDED.encrypted_token,label=EXCLUDED.label,cursor='',last_error=''""",
                    (session["user_id"], encrypted, label))
        except Exception:
            # Never echo credentials, provider bodies, URLs, or exception details.
            raise provider_error("Gumroad okuma bağlantısı kurulamadı. Panelden yeniden deneyin.") from None
        response = redirect("/?gumroad=connected")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
