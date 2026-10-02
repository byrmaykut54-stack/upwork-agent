import os, sqlite3, secrets, json, datetime
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from agent.pipeline import run_pipeline

app = Flask(__name__, static_folder="web", static_url_path="")
app.secret_key = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") == "1")
DB = os.environ.get("DATABASE_PATH", "/tmp/upwork_agent.db")
TRIAL_SCAN_LIMIT = 10

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,plan TEXT NOT NULL DEFAULT 'trial',
      scans_used INTEGER NOT NULL DEFAULT 0)""")
    cols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        if "password" in cols:
            for row in c.execute("SELECT id,password FROM users").fetchall():
                c.execute("UPDATE users SET password_hash=? WHERE id=?",
                          (generate_password_hash(row["password"]), row["id"]))
    for sql in [
      """CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,
        external_id TEXT,title TEXT NOT NULL,url TEXT,description TEXT,
        score INTEGER DEFAULT 0,status TEXT DEFAULT 'new',payload TEXT NOT NULL,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""",
      """CREATE TABLE IF NOT EXISTS proposals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,job_id INTEGER NOT NULL,
        body TEXT NOT NULL,status TEXT DEFAULT 'draft',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""",
      """CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,
        title TEXT NOT NULL,body TEXT NOT NULL,kind TEXT DEFAULT 'info',
        read INTEGER DEFAULT 0,created_at TEXT NOT NULL)""",
      """CREATE TABLE IF NOT EXISTS settings(
        user_id INTEGER PRIMARY KEY,min_hourly REAL DEFAULT 15,min_fixed REAL DEFAULT 100,
        keywords TEXT DEFAULT 'automation,google sheets,excel,ai,chatgpt,api,web scraping',
        excludes TEXT DEFAULT 'adult,gambling,illegal')"""
    ]: c.execute(sql)
    c.commit(); c.close()

def now(): return datetime.datetime.utcnow().replace(microsecond=0).isoformat()+"Z"
def user_payload(u):
    return {"email":u["email"],"plan":u["plan"],"scans_used":u["scans_used"]}
def current_user():
    uid=session.get("user_id")
    if not uid: return None
    c=db(); u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone(); c.close()
    return u

def auth_required():
    if not session.get("user_id"): return jsonify(error="Giriş gerekli."),401
    return None

@app.get("/health")
def health(): return {"status":"ok","service":"mexay","version":"1.0"}

@app.get("/")
def home(): return send_from_directory("web","index.html")

@app.post("/api/auth/register")
def register():
    d=request.get_json(silent=True) or {}; email=str(d.get("email","")).strip().lower(); password=d.get("password","")
    if "@" not in email or not isinstance(password,str) or len(password)<8:
        return jsonify(error="Geçerli e-posta ve en az 8 karakterli şifre gerekli."),400
    c=db()
    try:
        cur=c.execute("INSERT INTO users(email,password_hash) VALUES(?,?)",(email,generate_password_hash(password)))
        uid=cur.lastrowid
        c.execute("INSERT INTO settings(user_id) VALUES(?)",(uid,))
        c.execute("INSERT INTO notifications(user_id,title,body,kind,created_at) VALUES(?,?,?,?,?)",
                  (uid,"MexAy hazır","Hesabınız oluşturuldu. İlk taramanızı başlatabilirsiniz.","success",now()))
        c.commit()
    except sqlite3.IntegrityError:
        c.close(); return jsonify(error="Bu e-posta zaten kayıtlı."),409
    session.clear(); session["user_id"]=uid; c.close()
    return jsonify(ok=True,user={"email":email,"plan":"trial","scans_used":0})

@app.post("/api/auth/login")
def login():
    d=request.get_json(silent=True) or {}; email=str(d.get("email","")).strip().lower(); password=d.get("password","")
    c=db(); u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone(); c.close()
    if not u or not isinstance(password,str) or not check_password_hash(u["password_hash"],password):
        return jsonify(error="E-posta veya şifre hatalı."),401
    session.clear(); session["user_id"]=u["id"]; return jsonify(ok=True,user=user_payload(u))

@app.post("/api/auth/logout")
def logout(): session.clear(); return jsonify(ok=True)

@app.get("/api/me")
def me():
    u=current_user()
    if not u: session.clear(); return jsonify(authenticated=False)
    return jsonify(authenticated=True,user=user_payload(u))

@app.get("/api/dashboard")
def dashboard():
    if (e:=auth_required()): return e
    uid=session["user_id"]; c=db()
    u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    jobs=c.execute("SELECT COUNT(*) n FROM jobs WHERE user_id=?",(uid,)).fetchone()["n"]
    saved=c.execute("SELECT COUNT(*) n FROM jobs WHERE user_id=? AND status='saved'",(uid,)).fetchone()["n"]
    proposals=c.execute("SELECT COUNT(*) n FROM proposals WHERE user_id=?",(uid,)).fetchone()["n"]
    unread=c.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read=0",(uid,)).fetchone()["n"]
    c.close(); lim=TRIAL_SCAN_LIMIT if u["plan"]=="trial" else 1000
    return jsonify(user=user_payload(u),stats={"jobs":jobs,"saved":saved,"proposals":proposals,"unread":unread,
      "scan_limit":lim,"scan_remaining":max(0,lim-u["scans_used"])})

@app.post("/api/scan")
def scan():
    if (e:=auth_required()): return e
    d=request.get_json(silent=True) or {}; jobs=d.get("jobs",[])
    if not isinstance(jobs,list): return jsonify(error="jobs alanı liste olmalı."),400
    c=db(); u=c.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
    lim=TRIAL_SCAN_LIMIT if u["plan"]=="trial" else 1000
    if u["scans_used"]>=lim:
        c.close(); return jsonify(error="Aylık tarama kotanız doldu.",quota={"used":u["scans_used"],"limit":lim}),429
    try: result=run_pipeline(jobs,connects_balance=int(d.get("connects_balance",0)))
    except Exception:
        c.close(); return jsonify(error="Tarama sırasında beklenmeyen bir sunucu hatası oluştu."),500
    ts=now()
    for j in result:
        payload=json.dumps(j,ensure_ascii=False)
        c.execute("INSERT INTO jobs(user_id,external_id,title,url,description,score,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (session["user_id"],str(j.get("id") or j.get("job_id") or ""),j.get("title","İsimsiz ilan"),j.get("url",""),
                   j.get("description",""),int(j.get("score",0)), "new",payload,ts,ts))
    c.execute("UPDATE users SET scans_used=scans_used+1 WHERE id=?",(session["user_id"],))
    c.execute("INSERT INTO notifications(user_id,title,body,kind,created_at) VALUES(?,?,?,?,?)",
              (session["user_id"],"Tarama tamamlandı",f"{len(result)} ilan analiz edildi.","success",ts))
    c.commit(); used=u["scans_used"]+1; c.close()
    return jsonify(result=result,quota={"used":used,"limit":lim})

@app.get("/api/jobs")
def list_jobs():
    if (e:=auth_required()): return e
    c=db(); rows=c.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY score DESC,created_at DESC",(session["user_id"],)).fetchall(); c.close()
    out=[]
    for r in rows:
        j=json.loads(r["payload"]); j.update(id=r["id"],status=r["status"],created_at=r["created_at"]); out.append(j)
    return jsonify(jobs=out)

@app.post("/api/jobs/import")
def import_jobs():
    if (e:=auth_required()): return e
    d=request.get_json(silent=True) or {}; jobs=d.get("jobs",[])
    if not isinstance(jobs,list) or not jobs: return jsonify(error="En az bir ilan gerekli."),400
    c=db(); ts=now(); added=0
    for j in jobs[:100]:
        if not isinstance(j,dict): continue
        title=str(j.get("title","İsimsiz ilan"))
        c.execute("INSERT INTO jobs(user_id,external_id,title,url,description,score,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (session["user_id"],str(j.get("id","")),title,j.get("url",""),j.get("description",""),int(j.get("score",0)), "imported",json.dumps(j,ensure_ascii=False),ts,ts)); added+=1
    c.commit(); c.close(); return jsonify(ok=True,added=added)

@app.post("/api/jobs/<int:job_id>/save")
def save_job(job_id):
    if (e:=auth_required()): return e
    c=db(); r=c.execute("SELECT status FROM jobs WHERE id=? AND user_id=?",(job_id,session["user_id"])).fetchone()
    if not r: c.close(); return jsonify(error="İlan bulunamadı."),404
    status="new" if r["status"]=="saved" else "saved"; c.execute("UPDATE jobs SET status=?,updated_at=? WHERE id=?",(status,now(),job_id)); c.commit(); c.close()
    return jsonify(ok=True,status=status)

@app.get("/api/proposals")
def list_proposals():
    if (e:=auth_required()): return e
    c=db(); rows=c.execute("""SELECT p.*,j.title,j.url FROM proposals p JOIN jobs j ON j.id=p.job_id
                              WHERE p.user_id=? ORDER BY p.updated_at DESC""",(session["user_id"],)).fetchall(); c.close()
    return jsonify(proposals=[dict(r) for r in rows])

@app.post("/api/proposals")
def create_proposal():
    if (e:=auth_required()): return e
    d=request.get_json(silent=True) or {}; job_id=d.get("job_id")
    c=db(); r=c.execute("SELECT payload FROM jobs WHERE id=? AND user_id=?",(job_id,session["user_id"])).fetchone()
    if not r: c.close(); return jsonify(error="İlan bulunamadı."),404
    j=json.loads(r["payload"]); from agent.proposal import build_proposal
    profile=json.loads(open("agent/profile.json",encoding="utf-8").read()); body=build_proposal(j,profile); ts=now()
    cur=c.execute("INSERT INTO proposals(user_id,job_id,body,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                  (session["user_id"],job_id,body,"draft",ts,ts))
    c.commit(); pid=cur.lastrowid; c.close(); return jsonify(ok=True,id=pid,body=body,status="draft")

@app.patch("/api/proposals/<int:proposal_id>")
def update_proposal(proposal_id):
    if (e:=auth_required()): return e
    d=request.get_json(silent=True) or {}; status=str(d.get("status","draft"))
    allowed={"draft","review","approved","submitted","replied","won","lost","archived"}
    if status not in allowed: return jsonify(error="Geçersiz durum."),400
    c=db(); r=c.execute("SELECT id FROM proposals WHERE id=? AND user_id=?",(proposal_id,session["user_id"])).fetchone()
    if not r: c.close(); return jsonify(error="Teklif bulunamadı."),404
    c.execute("UPDATE proposals SET status=?,updated_at=? WHERE id=?",(status,now(),proposal_id)); c.commit(); c.close(); return jsonify(ok=True,status=status)

@app.get("/api/notifications")
def notifications():
    if (e:=auth_required()): return e
    c=db(); rows=c.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",(session["user_id"],)).fetchall(); c.close()
    return jsonify(notifications=[dict(r) for r in rows])

@app.post("/api/notifications/read")
def notifications_read():
    if (e:=auth_required()): return e
    c=db(); c.execute("UPDATE notifications SET read=1 WHERE user_id=?",(session["user_id"],)); c.commit(); c.close(); return jsonify(ok=True)

@app.get("/api/settings")
def get_settings():
    if (e:=auth_required()): return e
    c=db(); r=c.execute("SELECT * FROM settings WHERE user_id=?",(session["user_id"],)).fetchone(); c.close()
    return jsonify(settings={"min_hourly":r["min_hourly"],"min_fixed":r["min_fixed"],"keywords":r["keywords"].split(","),"excludes":r["excludes"].split(",")})

@app.put("/api/settings")
def put_settings():
    if (e:=auth_required()): return e
    d=request.get_json(silent=True) or {}; keywords=d.get("keywords",[]); excludes=d.get("excludes",[])
    try: mh=float(d.get("min_hourly",15)); mf=float(d.get("min_fixed",100))
    except: return jsonify(error="Bütçe değerleri sayısal olmalı."),400
    c=db(); c.execute("INSERT OR REPLACE INTO settings(user_id,min_hourly,min_fixed,keywords,excludes) VALUES(?,?,?,?,?)",
                      (session["user_id"],mh,mf,",".join(map(str,keywords)),",".join(map(str,excludes)))); c.commit(); c.close()
    return jsonify(ok=True)

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
