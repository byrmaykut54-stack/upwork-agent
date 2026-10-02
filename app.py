import os, sqlite3, hashlib, secrets
from flask import Flask, request, jsonify, session, send_from_directory
from agent.pipeline import run_pipeline
app=Flask(__name__,static_folder="web",static_url_path="")
app.secret_key=os.environ.get("SESSION_SECRET",secrets.token_hex(32))
DB=os.environ.get("DATABASE_PATH","/tmp/upwork_agent.db")
def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 c=db(); c.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,plan TEXT NOT NULL DEFAULT 'trial')"); c.commit(); c.close()
def pw(v): return hashlib.sha256(v.encode()).hexdigest()
@app.get("/health")
def health(): return {"status":"ok","service":"upwork-agent-pro"}
@app.get("/")
def home(): return send_from_directory("web","index.html")
@app.post("/api/auth/register")
def register():
 d=request.get_json() or {}; email=d.get("email","").strip().lower(); password=d.get("password","")
 if not email or len(password)<6: return jsonify(error="Geçerli e-posta ve en az 6 karakterli şifre gerekli."),400
 c=db()
 try: cur=c.execute("INSERT INTO users(email,password) VALUES(?,?)",(email,pw(password))); c.commit()
 except sqlite3.IntegrityError: c.close(); return jsonify(error="Bu e-posta zaten kayıtlı."),409
 session["user_id"]=cur.lastrowid; session["email"]=email; c.close(); return jsonify(ok=True,user={"email":email,"plan":"trial"})
@app.post("/api/auth/login")
def login():
 d=request.get_json() or {}; c=db(); u=c.execute("SELECT * FROM users WHERE email=? AND password=?",(d.get("email","").strip().lower(),pw(d.get("password","")))).fetchone(); c.close()
 if not u: return jsonify(error="E-posta veya şifre hatalı."),401
 session["user_id"]=u["id"]; session["email"]=u["email"]; return jsonify(ok=True,user={"email":u["email"],"plan":u["plan"]})
@app.post("/api/auth/logout")
def logout(): session.clear(); return jsonify(ok=True)
@app.get("/api/me")
def me():
 if "user_id" not in session: return jsonify(authenticated=False)
 c=db(); u=c.execute("SELECT email,plan FROM users WHERE id=?",(session["user_id"],)).fetchone(); c.close(); return jsonify(authenticated=True,user=dict(u))
@app.post("/api/scan")
def scan():
 if "user_id" not in session: return jsonify(error="Giriş gerekli."),401
 d=request.get_json() or {}; return jsonify(run_pipeline(d.get("jobs",[]),d.get("connects_balance",0)))
init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))