import os, sqlite3, secrets
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from agent.pipeline import run_pipeline

app = Flask(__name__, static_folder="web", static_url_path="")
app.secret_key = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1",
)
DB = os.environ.get("DATABASE_PATH", "/tmp/upwork_agent.db")
TRIAL_SCAN_LIMIT = 10

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'trial',
        scans_used INTEGER NOT NULL DEFAULT 0
    )""")
    # Compatibility with the original MVP database.
    cols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        old = c.execute("SELECT id,password FROM users").fetchall()
        for row in old:
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(row["password"]), row["id"]))
    if "scans_used" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN scans_used INTEGER NOT NULL DEFAULT 0")
    c.commit()
    c.close()

def user_payload(u):
    return {"email": u["email"], "plan": u["plan"], "scans_used": u["scans_used"]}

@app.get("/health")
def health():
    return {"status": "ok", "service": "upwork-agent-pro"}

@app.get("/")
def home():
    return send_from_directory("web", "index.html")

@app.post("/api/auth/register")
def register():
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    if not email or "@" not in email or len(password) < 8:
        return jsonify(error="Geçerli e-posta ve en az 8 karakterli şifre gerekli."), 400
    c = db()
    try:
        cur = c.execute(
            "INSERT INTO users(email,password_hash) VALUES(?,?)",
            (email, generate_password_hash(password))
        )
        c.commit()
    except sqlite3.IntegrityError:
        c.close()
        return jsonify(error="Bu e-posta zaten kayıtlı."), 409
    session.clear()
    session["user_id"] = cur.lastrowid
    c.close()
    return jsonify(ok=True, user={"email": email, "plan": "trial", "scans_used": 0})

@app.post("/api/auth/login")
def login():
    d = request.get_json() or {}
    email = d.get("email", "").strip().lower()
    c = db()
    u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    c.close()
    if not u or not check_password_hash(u["password_hash"], d.get("password", "")):
        return jsonify(error="E-posta veya şifre hatalı."), 401
    session.clear()
    session["user_id"] = u["id"]
    return jsonify(ok=True, user=user_payload(u))

@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/me")
def me():
    if "user_id" not in session:
        return jsonify(authenticated=False)
    c = db()
    u = c.execute("SELECT email,plan,scans_used FROM users WHERE id=?", (session["user_id"],)).fetchone()
    c.close()
    if not u:
        session.clear()
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, user=user_payload(u))

@app.post("/api/scan")
def scan():
    if "user_id" not in session:
        return jsonify(error="Giriş gerekli."), 401
    d = request.get_json() or {}
    jobs = d.get("jobs", [])
    if not isinstance(jobs, list):
        return jsonify(error="jobs alanı liste olmalı."), 400
    try:
        connects_balance = int(d.get("connects_balance", 0))
    except (TypeError, ValueError):
        connects_balance = 0
    c = db()
    u = c.execute("SELECT plan,scans_used FROM users WHERE id=?", (session["user_id"],)).fetchone()
    limit = TRIAL_SCAN_LIMIT if u["plan"] == "trial" else 1000
    if u["scans_used"] >= limit:
        c.close()
        return jsonify(error="Aylık tarama kotanız doldu.", quota={"used": u["scans_used"], "limit": limit}), 429
    try:
        result = run_pipeline(jobs, connects_balance=connects_balance)
    except Exception:
        c.close()
        return jsonify(error="Tarama sırasında beklenmeyen bir sunucu hatası oluştu."), 500
    c.execute("UPDATE users SET scans_used=scans_used+1 WHERE id=?", (session["user_id"],))
    c.commit()
    used = u["scans_used"] + 1
    c.close()
    return jsonify(result=result, quota={"used": used, "limit": limit})

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
