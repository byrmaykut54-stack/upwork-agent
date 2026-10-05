import os, json, datetime, secrets, urllib.parse, urllib.request, hashlib, math, re, time
from pathlib import Path
from collections import defaultdict, deque
import psycopg
from psycopg.rows import dict_row
from flask import Flask, request, jsonify, session, send_from_directory, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from agent.pipeline import run_pipeline
import central
import mailer

app = Flask(__name__, static_folder="web", static_url_path="")
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=2_000_000,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
)

@app.before_request
def validate_request():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("Origin", "")
        expected = os.environ.get("APP_BASE_URL", request.host_url).rstrip("/")
        if origin and origin.rstrip("/") != expected:
            return jsonify(error="İstek kaynağı doğrulanamadı."), 403
        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(error="JSON gövdesi bir nesne olmalı."), 400

@app.errorhandler(psycopg.Error)
def database_error(error):
    app.logger.error("Database operation failed: %s", type(error).__name__)
    return jsonify(error="Veritabanına şu anda erişilemiyor. Lütfen tekrar deneyin."), 503

@app.errorhandler(413)
def payload_too_large(error):
    return jsonify(error="İstek gövdesi çok büyük."), 413

AUTH_ATTEMPTS = defaultdict(deque)

def auth_rate_limit(email, limit=10, window=60):
    key = (request.endpoint, request.remote_addr, email)
    entries = AUTH_ATTEMPTS[key]
    current = time.monotonic()
    while entries and entries[0] <= current - window:
        entries.popleft()
    if len(entries) >= limit:
        return jsonify(error="Çok fazla deneme. Lütfen kısa süre sonra tekrar deneyin."), 429
    entries.append(current)
    if len(AUTH_ATTEMPTS) > 10000:
        for old in list(AUTH_ATTEMPTS):
            if not AUTH_ATTEMPTS[old] or AUTH_ATTEMPTS[old][-1] <= current - window:
                del AUTH_ATTEMPTS[old]
    return None

def valid_email(email):
    return isinstance(email, str) and len(email) <= 254 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) is not None

def start_session(u):
    csrf = session.get("csrf") or secrets.token_urlsafe(32)
    session.clear()
    session["csrf"] = csrf
    session["user_id"] = u["id"]
    session["auth_version"] = hashlib.sha256(u["password_hash"].encode()).hexdigest()


@app.before_request
def csrf_guard():
    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        payload = request.get_json(silent=True)
        if payload is not None and not isinstance(payload, dict):
            return jsonify(error="İstek içeriği bir JSON nesnesi olmalı."), 400
        expected = session.get("csrf", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            return jsonify(error="Güvenlik oturumu yenilenmeli. Sayfayı yenileyin."), 403

@app.get("/api/session")
def session_info():
    session.setdefault("csrf", secrets.token_urlsafe(32))
    return jsonify(csrf=session["csrf"], session_ready=bool(os.environ.get("SESSION_SECRET")), google_ready=bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET") and os.environ.get("GOOGLE_REDIRECT_URI")))

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.is_secure or os.environ.get("COOKIE_SECURE", "1") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL tanımlı değil. Render PostgreSQL bağlantısını ekleyin.")

PLAN_LIMITS = {
    "trial": {"scans": 10, "proposals": 10},
    "pro": {"scans": 500, "proposals": 1000},
    "agency": {"scans": 5000, "proposals": 10000},
}

def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)

def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)

def period():
    return now().strftime("%Y-%m")

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id BIGSERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'trial',
            usage_period TEXT NOT NULL DEFAULT '',
            scans_used INTEGER NOT NULL DEFAULT 0,
            proposals_used INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS jobs(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            external_id TEXT, title TEXT NOT NULL, url TEXT, description TEXT,
            score INTEGER DEFAULT 0, status TEXT DEFAULT 'new', payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS proposals(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            body TEXT NOT NULL, status TEXT DEFAULT 'draft',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS notifications(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, body TEXT NOT NULL, kind TEXT DEFAULT 'info',
            read BOOLEAN DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS password_reset_tokens(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings(
            user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            min_hourly DOUBLE PRECISION DEFAULT 15,
            min_fixed DOUBLE PRECISION DEFAULT 100,
            keywords TEXT DEFAULT 'automation,google sheets,excel,ai,chatgpt,api,web scraping',
            excludes TEXT DEFAULT 'adult,gambling,illegal'
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_score ON jobs(user_id, score DESC, created_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_proposals_user_updated ON proposals(user_id, updated_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS user_profiles(
            user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            facts JSONB NOT NULL DEFAULT '{}'::jsonb
        )""")
        central.initialize(c)

def profile_for(c, uid):
    row = c.execute("SELECT facts FROM user_profiles WHERE user_id=%s", (uid,)).fetchone()
    return row["facts"] if row else {}

def scan_config(c, uid):
    config = json.loads((Path(__file__).parent / "agent/config.json").read_text())
    row = c.execute("SELECT * FROM settings WHERE user_id=%s", (uid,)).fetchone()
    if row:
        config.update(min_hourly_rate_usd=row["min_hourly"], min_fixed_budget_usd=row["min_fixed"],
                      keywords=[x.strip() for x in row["keywords"].split(",") if x.strip()],
                      exclude_keywords=[x.strip() for x in row["excludes"].split(",") if x.strip()])
    return config


def normalize_usage(c, u):
    current = period()
    if u["usage_period"] != current:
        c.execute("UPDATE users SET usage_period=%s, scans_used=0, proposals_used=0 WHERE id=%s",
                  (current, u["id"]))
        u = dict(u)
        u["usage_period"] = current
        u["scans_used"] = 0
        u["proposals_used"] = 0
    return u

def plan_limits(plan):
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["trial"])

def user_payload(u):
    limits = plan_limits(u["plan"])
    return {
        "email": u["email"], "plan": u["plan"],
        "scans_used": u["scans_used"], "proposals_used": u["proposals_used"],
        "scan_limit": limits["scans"], "proposal_limit": limits["proposals"],
        "scan_remaining": max(0, limits["scans"] - u["scans_used"]),
        "proposal_remaining": max(0, limits["proposals"] - u["proposals_used"]),
    }

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=%s", (uid,)).fetchone()
        if not u or session.get("auth_version") != hashlib.sha256(u["password_hash"].encode()).hexdigest():
            session.pop("user_id", None)
            session.pop("auth_version", None)
            return None
        return normalize_usage(c, u) if u else None

def auth_required():
    if not current_user():
        return jsonify(error="Giriş gerekli."), 401
    return None

@app.get("/health")
def health():
    try:
        with db() as c:
            c.execute("SELECT 1")
        return {"status": "ok", "service": "mexay", "version": "3.0", "database": "postgresql"}
    except Exception:
        return {"status": "error", "service": "mexay", "database": "unavailable"}, 503

@app.get("/")
def home():
    return send_from_directory("web", "index.html")

@app.post("/api/auth/register")
def register():
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    password = d.get("password", "")
    if not valid_email(email) or not isinstance(password, str) or not 8 <= len(password) <= 128:
        return jsonify(error="Geçerli e-posta ve en az 8 karakterli şifre gerekli."), 400
    if (e := auth_rate_limit(email, limit=5)): return e
    with db() as c:
        u = c.execute("""INSERT INTO users(email,password_hash,plan,usage_period)
                         VALUES(%s,%s,'trial',%s) ON CONFLICT(email) DO NOTHING RETURNING *""",
                      (email, generate_password_hash(password), period())).fetchone()
        if not u:
            return jsonify(error="Bu e-posta zaten kayıtlı."), 409
        c.execute("INSERT INTO settings(user_id) VALUES(%s)", (u["id"],))
        c.execute("""INSERT INTO notifications(user_id,title,body,kind) VALUES(%s,%s,%s,%s)""",
                  (u["id"], "MexAy hazır", "Hesabınız oluşturuldu. Platformlar bölümünden hesaplarınızı bağlayın.", "success"))
    start_session(u)
    return jsonify(ok=True, user=user_payload(u))

@app.post("/api/auth/login")
def login():
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    password = d.get("password", "")
    if not valid_email(email) or not isinstance(password, str) or not 1 <= len(password) <= 128:
        return jsonify(error="Geçerli e-posta ve şifre gerekli."), 400
    if (e := auth_rate_limit(email)): return e
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
        if u:
            u = normalize_usage(c, u)
    if not u or not isinstance(password, str) or not check_password_hash(u["password_hash"], password):
        return jsonify(error="E-posta veya şifre hatalı."), 401
    start_session(u)
    return jsonify(ok=True, user=user_payload(u))

@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/me")
def me():
    u = current_user()
    if not u:
        session.pop("user_id", None)
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, user=user_payload(u))

@app.get("/api/dashboard")
def dashboard():
    if (e := auth_required()): return e
    u = current_user()
    with db() as c:
        jobs = c.execute("SELECT COUNT(*) AS n FROM jobs WHERE user_id=%s", (u["id"],)).fetchone()["n"]
        saved = c.execute("SELECT COUNT(*) AS n FROM jobs WHERE user_id=%s AND status='saved'", (u["id"],)).fetchone()["n"]
        proposals = c.execute("SELECT COUNT(*) AS n FROM proposals WHERE user_id=%s", (u["id"],)).fetchone()["n"]
        unread = c.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=%s AND read=FALSE", (u["id"],)).fetchone()["n"]
    return jsonify(user=user_payload(u), stats={"jobs": jobs, "saved": saved, "proposals": proposals,
        "unread": unread, "scan_limit": plan_limits(u["plan"])["scans"],
        "scan_remaining": max(0, plan_limits(u["plan"])["scans"] - u["scans_used"])})

@app.get("/api/plans")
def plans():
    return jsonify(plans={
        "trial": {"scans": 10, "proposals": 10, "payment_required": False},
        "pro": {"scans": 500, "proposals": 1000, "payment_required": True},
        "agency": {"scans": 5000, "proposals": 10000, "payment_required": True},
    })

@app.post("/api/scan")
def scan():
    if (e := auth_required()): return e
    d = request.get_json(silent=True) or {}
    jobs = d.get("jobs", [])
    if not isinstance(jobs, list) or not jobs or len(jobs) > 100 or any(not isinstance(j, dict) for j in jobs):
        return jsonify(error="1 ile 100 arasında ilan nesnesi gerekli."), 400
    try:
        connects = int(d.get("connects_balance", 0))
        if connects < 0: raise ValueError()
    except (ValueError, TypeError):
        return jsonify(error="Connects bakiyesi sıfır veya pozitif bir tam sayı olmalı."), 400
    with db() as c:
        u = normalize_usage(c, c.execute("SELECT * FROM users WHERE id=%s FOR UPDATE", (session["user_id"],)).fetchone())
        lim = plan_limits(u["plan"])["scans"]
        if u["scans_used"] >= lim:
            return jsonify(error="Aylık tarama kotanız doldu.", quota={"used": u["scans_used"], "limit": lim}), 429
        try:
            result = run_pipeline(jobs, config=scan_config(c, u["id"]), profile=profile_for(c, u["id"]), connects_balance=connects)
        except (ValueError, TypeError, AttributeError, IndexError):
            return jsonify(error="İlan verilerinin biçimini kontrol edin."), 400
        for j in result:
            c.execute("""INSERT INTO jobs(user_id,external_id,title,url,description,score,status,payload)
                         VALUES(%s,%s,%s,%s,%s,%s,'new',%s)""",
                      (u["id"], str(j.get("id") or j.get("job_id") or ""), j.get("title", "İsimsiz ilan"),
                       j.get("url", ""), j.get("description", ""), int(j.get("score", 0)), json.dumps(j, ensure_ascii=False)))
        c.execute("UPDATE users SET scans_used=scans_used+1 WHERE id=%s", (u["id"],))
        c.execute("""INSERT INTO notifications(user_id,title,body,kind)
                     VALUES(%s,%s,%s,%s)""",
                  (u["id"], "Tarama tamamlandı", f"{len(result)} ilan analiz edildi.", "success"))
        used = u["scans_used"] + 1
    return jsonify(result=result, quota={"used": used, "limit": lim})

@app.get("/api/jobs")
def list_jobs():
    if (e := auth_required()): return e
    with db() as c:
        rows = c.execute("SELECT * FROM jobs WHERE user_id=%s ORDER BY score DESC, created_at DESC",
                         (session["user_id"],)).fetchall()
    out = []
    for r in rows:
        j = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
        j.update(id=r["id"], status=r["status"], created_at=r["created_at"].isoformat())
        out.append(j)
    return jsonify(jobs=out)

@app.post("/api/jobs/import")
def import_jobs():
    if (e := auth_required()): return e
    d = request.get_json(silent=True) or {}
    jobs = d.get("jobs", [])
    if not isinstance(jobs, list) or not jobs:
        return jsonify(error="En az bir ilan gerekli."), 400
    # Imports go through the same analysis and quota rules as a scan.
    return scan()

@app.post("/api/jobs/<int:job_id>/save")
def save_job(job_id):
    if (e := auth_required()): return e
    with db() as c:
        r = c.execute("SELECT status FROM jobs WHERE id=%s AND user_id=%s", (job_id, session["user_id"])).fetchone()
        if not r: return jsonify(error="İlan bulunamadı."), 404
        status = "new" if r["status"] == "saved" else "saved"
        c.execute("UPDATE jobs SET status=%s,updated_at=NOW() WHERE id=%s", (status, job_id))
    return jsonify(ok=True, status=status)

@app.get("/api/proposals")
def list_proposals():
    if (e := auth_required()): return e
    with db() as c:
        rows = c.execute("""SELECT p.*,j.title,j.url FROM proposals p JOIN jobs j ON j.id=p.job_id
                            WHERE p.user_id=%s ORDER BY p.updated_at DESC""", (session["user_id"],)).fetchall()
    return jsonify(proposals=[dict(r) for r in rows])

@app.post("/api/proposals")
def create_proposal():
    if (e := auth_required()): return e
    d = request.get_json(silent=True) or {}
    job_id = d.get("job_id")
    with db() as c:
        u = normalize_usage(c, c.execute("SELECT * FROM users WHERE id=%s FOR UPDATE", (session["user_id"],)).fetchone())
        lim = plan_limits(u["plan"])["proposals"]
        if u["proposals_used"] >= lim:
            return jsonify(error="Aylık teklif hazırlama kotanız doldu.", quota={"used": u["proposals_used"], "limit": lim}), 429
        r = c.execute("SELECT payload FROM jobs WHERE id=%s AND user_id=%s", (job_id, session["user_id"])).fetchone()
        if not r: return jsonify(error="İlan bulunamadı."), 404
        j = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
        from agent.proposal import build_proposal
        profile = profile_for(c, u["id"])
        body = build_proposal(j, profile)
        cur = c.execute("""INSERT INTO proposals(user_id,job_id,body,status)
                           VALUES(%s,%s,%s,'draft') RETURNING id""", (u["id"], job_id, body))
        pid = cur.fetchone()["id"]
        c.execute("UPDATE users SET proposals_used=proposals_used+1 WHERE id=%s", (u["id"],))
    return jsonify(ok=True, id=pid, body=body, status="draft")

@app.patch("/api/proposals/<int:proposal_id>")
def update_proposal(proposal_id):
    if (e := auth_required()): return e
    d = request.get_json(silent=True) or {}
    status = str(d.get("status", "draft"))
    allowed = {"draft", "review", "approved", "replied", "won", "lost", "archived"}
    if status not in allowed: return jsonify(error="Teklif gönderimi bu ekrandan yapılamaz. Önce açık onay gereklidir."), 400
    body = d.get("body")
    if body is not None and (not isinstance(body, str) or not body.strip() or len(body) > 20000):
        return jsonify(error="Teklif metni 1–20000 karakter olmalı."), 400
    with db() as c:
        r = c.execute("SELECT id FROM proposals WHERE id=%s AND user_id=%s", (proposal_id, session["user_id"])).fetchone()
        if not r: return jsonify(error="Teklif bulunamadı."), 404
        c.execute("UPDATE proposals SET status=%s,body=COALESCE(%s,body),updated_at=NOW() WHERE id=%s", (status, body, proposal_id))
    return jsonify(ok=True, status=status)


@app.post("/api/proposals/<int:proposal_id>/submit")
def submit_proposal(proposal_id):
    if (e := auth_required()): return e
    d = request.get_json(silent=True) or {}
    if d.get("confirm") is not True:
        return jsonify(error="Teklif gönderimi için açık kullanıcı onayı gereklidir.", requires_confirmation=True), 400
    with db() as c:
        p = c.execute("""SELECT p.id,p.status,j.title FROM proposals p
                         JOIN jobs j ON j.id=p.job_id
                         WHERE p.id=%s AND p.user_id=%s""",
                      (proposal_id, session["user_id"])).fetchone()
        if not p:
            return jsonify(error="Teklif bulunamadı."), 404
        if p["status"] != "approved":
            return jsonify(error="Teklif gönderilmeden önce 'approved' durumuna alınmalıdır."), 409
    return jsonify(error="Upwork bağlantısı henüz kurulmadı; gerçek gönderim yapılmadı.",
                   submitted=False, requires_upwork_connection=True), 409

@app.get("/api/notifications")
def notifications():
    if (e := auth_required()): return e
    with db() as c:
        rows = c.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 50",
                         (session["user_id"],)).fetchall()
    return jsonify(notifications=[dict(r) for r in rows])

@app.post("/api/notifications/read")
def notifications_read():
    if (e := auth_required()): return e
    with db() as c:
        c.execute("UPDATE notifications SET read=TRUE WHERE user_id=%s", (session["user_id"],))
    return jsonify(ok=True)

@app.get("/api/settings")
def get_settings():
    if (e := auth_required()): return e
    with db() as c:
        r = c.execute("SELECT * FROM settings WHERE user_id=%s", (session["user_id"],)).fetchone()
    return jsonify(settings={"min_hourly": r["min_hourly"], "min_fixed": r["min_fixed"],
                             "keywords": r["keywords"].split(","), "excludes": r["excludes"].split(",")})

@app.put("/api/settings")
def put_settings():
    if (e := auth_required()): return e
    d = request.get_json(silent=True) or {}
    keywords, excludes = d.get("keywords", []), d.get("excludes", [])
    if any(not isinstance(v, list) or len(v) > 100 or any(not isinstance(x, str) or len(x) > 120 for x in v) for v in (keywords, excludes)):
        return jsonify(error="Anahtar ve hariç kelimeler metin listeleri olmalı."), 400
    try:
        mh, mf = float(d.get("min_hourly", 15)), float(d.get("min_fixed", 100))
    except (TypeError, ValueError):
        return jsonify(error="Bütçe değerleri sayısal olmalı."), 400
    if not all(math.isfinite(v) and 0 <= v <= 1000000 for v in (mh, mf)):
        return jsonify(error="Bütçe değerleri sıfır veya pozitif olmalı."), 400
    with db() as c:
        c.execute("""INSERT INTO settings(user_id,min_hourly,min_fixed,keywords,excludes)
                     VALUES(%s,%s,%s,%s,%s)
                     ON CONFLICT(user_id) DO UPDATE SET min_hourly=EXCLUDED.min_hourly,
                     min_fixed=EXCLUDED.min_fixed,keywords=EXCLUDED.keywords,excludes=EXCLUDED.excludes""",
                  (session["user_id"], mh, mf, ",".join(map(str, keywords)), ",".join(map(str, excludes))))
    return jsonify(ok=True)

@app.post("/api/auth/forgot")
def forgot_password():
    d = request.get_json(silent=True) or {}
    email = str(d.get("email", "")).strip().lower()
    if not valid_email(email):
        return jsonify(error="Geçerli bir e-posta adresi girin."), 400
    if (e := auth_rate_limit(email, limit=3, window=300)): return e
    if not mailer.configured():
        return jsonify(error="Şifre yenileme e-posta servisi henüz yapılandırılmadı."), 503
    with db() as c:
        u = c.execute("SELECT id,email FROM users WHERE email=%s", (email,)).fetchone()
    generic = "Eğer bu e-posta kayıtlıysa, şifre yenileme bağlantısı gönderildi."
    if not u:
        return jsonify(ok=True, message=generic)
    base_url = os.environ.get("APP_BASE_URL", "https://upwork-agent-pro.onrender.com").rstrip("/")
    raw = secrets.token_urlsafe(32)
    token_hash = __import__("hashlib").sha256(raw.encode()).hexdigest()
    expires = now() + datetime.timedelta(minutes=30)
    with db() as c:
        c.execute("UPDATE password_reset_tokens SET used=TRUE WHERE user_id=%s AND used=FALSE", (u["id"],))
        c.execute("INSERT INTO password_reset_tokens(user_id,token_hash,expires_at) VALUES(%s,%s,%s)", (u["id"], token_hash, expires))
    reset_url = f"{base_url}/reset-password?token={urllib.parse.quote(raw)}"
    if not mailer.send(email, "MexAy Upwork Agent şifre yenileme",
                       f"Şifrenizi 30 dakika içinde yenileyin:\n{reset_url}\n\nBu isteği siz yapmadıysanız e-postayı yok sayın."):
        with db() as c:
            c.execute("UPDATE password_reset_tokens SET used=TRUE WHERE token_hash=%s", (token_hash,))
        return jsonify(error="Şifre yenileme e-postası gönderilemedi."), 502
    return jsonify(ok=True, message=generic)

@app.get("/reset-password")
def reset_password_page():
    return send_from_directory("web", "reset-password.html")

@app.post("/api/auth/reset-password")
def reset_password():
    d = request.get_json(silent=True) or {}
    token = str(d.get("token", ""))
    password = d.get("password", "")
    if not token or len(token) > 128 or not isinstance(password, str) or not 8 <= len(password) <= 128:
        return jsonify(error="Geçerli bağlantı ve en az 8 karakterli yeni şifre gerekli."), 400
    token_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
    with db() as c:
        row = c.execute("SELECT id,user_id FROM password_reset_tokens WHERE token_hash=%s AND used=FALSE AND expires_at>NOW() FOR UPDATE", (token_hash,)).fetchone()
        if not row: return jsonify(error="Şifre yenileme bağlantısı geçersiz veya süresi dolmuş."), 400
        c.execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(password), row["user_id"]))
        c.execute("UPDATE password_reset_tokens SET used=TRUE WHERE id=%s", (row["id"],))
        c.execute("UPDATE password_reset_tokens SET used=TRUE WHERE user_id=%s", (row["user_id"],))
    session.clear()
    return jsonify(ok=True, message="Şifreniz yenilendi.")

@app.get("/auth/google")
def google_login():
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "")
    if not client_id or not redirect_uri or not os.environ.get("GOOGLE_CLIENT_SECRET"):
        return redirect("/?auth_error=google_unavailable")
    state = secrets.token_urlsafe(32)
    session['google_state'] = state
    session['google_state_created'] = time.time()
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    })
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + params)

@app.get("/auth/google/callback")
def google_callback():
    expected = session.pop('google_state', '')
    created = session.pop('google_state_created', 0)
    received = request.args.get('state', '')
    if not expected or not received or not secrets.compare_digest(expected, received) or time.time() - created > 600:
        return redirect('/?auth_error=google_state')
    if request.args.get('error'):
        return redirect('/?auth_error=google_cancelled')
    code = request.args.get("code", "")
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "")
    if not code or not client_id or not client_secret or not redirect_uri:
        return "Google ile giriş yapılandırması eksik.", 400
    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read().decode())
        access_token = token_data.get("access_token")
        if not access_token:
            return "Google erişim anahtarı alınamadı.", 502
        info_req = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": "Bearer " + access_token},
        )
        with urllib.request.urlopen(info_req, timeout=10) as resp:
            info = json.loads(resp.read().decode())
    except Exception:
        return "Google hesabı doğrulanamadı.", 502

    email = str(info.get("email", "")).strip().lower()
    if not email or info.get("email_verified") is not True:
        return "Doğrulanmış Google e-postası gerekli.", 400

    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
        if not u:
            generated = secrets.token_urlsafe(32)
            u = c.execute(
                """INSERT INTO users(email,password_hash,plan,usage_period)
                   VALUES(%s,%s,'trial',%s) RETURNING *""",
                (email, generate_password_hash(generated), period()),
            ).fetchone()
            c.execute("INSERT INTO settings(user_id) VALUES(%s)", (u["id"],))
            c.execute(
                """INSERT INTO notifications(user_id,title,body,kind)
                   VALUES(%s,%s,%s,%s)""",
                (u["id"], "MexAy hazır", "Google hesabınızla kayıt tamamlandı.", "success"),
            )
        else:
            u = normalize_usage(c, u)
    start_session(u)
    return redirect("/")

@app.get('/api/capabilities')
def capabilities():
    return jsonify(google_login=all(os.getenv(x) for x in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI')),
                   password_reset=mailer.configured(), upwork_connected=False, automatic_submission=False)

@app.get('/api/profile')
def get_profile():
    if (e := auth_required()): return e
    with db() as c:
        return jsonify(profile=profile_for(c, session['user_id']))

@app.put('/api/profile')
def put_profile():
    if (e := auth_required()): return e
    facts = request.get_json(silent=True) or {}
    experience = facts.get('relevant_experience', [])
    proof = facts.get('proof', '')
    if not isinstance(experience, list) or len(experience) > 10 or any(not isinstance(x, str) or len(x) > 500 for x in experience) or not isinstance(proof, str) or len(proof) > 2000:
        return jsonify(error='Profil metinlerinin uzunluğunu ve biçimini kontrol edin.'), 400
    facts = {'relevant_experience': [x.strip() for x in experience if x.strip()], 'proof': proof.strip()}
    with db() as c:
        c.execute('INSERT INTO user_profiles(user_id,facts) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET facts=EXCLUDED.facts',
                  (session['user_id'], json.dumps(facts)))
    return jsonify(ok=True)

@app.get("/admin/reset")
def admin_reset_page():
    return """<!doctype html><html lang="tr"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MexAy Yönetici Sıfırlama</title><style>body{margin:0;background:#071020;color:#fff;font-family:Inter,system-ui;padding:28px}.box{max-width:420px;margin:10vh auto;background:#101d42;border:1px solid #2b3b65;border-radius:18px;padding:24px}input,button{width:100%;height:48px;box-sizing:border-box;border-radius:10px;margin-top:10px}input{background:#080f20;border:1px solid #33456f;color:#fff;padding:0 14px}button{border:0;background:#F5C451;color:#111;font-weight:800}.warn{color:#ffb0b8;font-size:13px;line-height:1.5}</style><div class="box"><h2>MexAy Yönetici Sıfırlama</h2><p class="warn">Bu işlem TÜM kullanıcı, iş, teklif, bildirim ve ayar kayıtlarını kalıcı olarak siler. Veritabanı tabloları korunur.</p><form method="post" action="/api/admin/reset-all"><input name="token" type="password" placeholder="Geçici yönetici anahtarı" required><input name="confirm" placeholder="MEXAY-RESET-ALL yazın" required><button type="submit">TÜM KAYITLARI SİL</button></form></div></html>"""

@app.post("/api/admin/reset-all")
def admin_reset_all():
    expected = os.environ.get("MEXAY_ADMIN_KEY", "")
    d = request.get_json(silent=True) or request.form
    token = request.headers.get("X-MexAy-Reset-Token") or d.get("token", "")
    confirm = d.get("confirm", "")
    if not expected or not secrets.compare_digest(str(token), expected):
        return jsonify(error="Geçersiz veya süresi dolmuş yönetici anahtarı."), 403
    if confirm != "MEXAY-RESET-ALL":
        return jsonify(error="Onay metni hatalı."), 400
    with db() as c:
        c.execute("TRUNCATE TABLE notifications, proposals, jobs, settings, users RESTART IDENTITY CASCADE")
    session.clear()
    if request.form:
        return "<!doctype html><meta name='viewport' content='width=device-width'><body style='font-family:system-ui;background:#071020;color:#fff;padding:40px;text-align:center'><h2>MexAy kayıtları temizlendi.</h2><p>Tüm kullanıcı ve uygulama kayıtları silindi. Tablo yapısı korundu.</p><a href='/' style='color:#F5C451'>Giriş ekranına dön</a></body>"
    return jsonify(ok=True, message="Tüm kullanıcı ve uygulama kayıtları temizlendi.", tables_preserved=True)

@app.get("/admin/reset")
def admin_reset_page_alias():
    return admin_reset_page()

central.register(app, db, auth_required, run_pipeline, profile_for)
init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
