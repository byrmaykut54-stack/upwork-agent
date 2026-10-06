"""Authenticated multi-channel workspace; provider calls are read-only."""
import csv
import io
import json
import os
import re
import psycopg
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, jsonify, request, session, Response

PLATFORMS = {
    "upwork": {"name": "Upwork", "url": "https://www.upwork.com/nx/find-work/", "mode": "api"},
    "gumroad": {"name": "Gumroad", "url": "https://gumroad.com/dashboard", "mode": "api"},
}
STATUSES = {"lead", "in_progress", "completed", "cancelled", "refunded", "partial_refund", "disputed"}
JOB_QUERY = """query { marketplaceJobPostingsSearch(searchType: USER_JOBS_SEARCH,
sortAttributes: [{field: RECENCY}]) { totalCount edges { node {
id title description ciphertext amount { displayValue currency } skills { name }
} } } }"""


class ProviderError(Exception):
    pass


def cipher():
    key = os.environ.get("INTEGRATION_ENCRYPTION_KEY", "")
    if not key:
        raise ProviderError("Bağlantı şifreleme anahtarı sunucuda henüz yapılandırılmadı.")
    try:
        return Fernet(key.encode())
    except ValueError:
        raise ProviderError("Bağlantı şifreleme yapılandırması geçersiz.") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def remote_json(platform, token, path=None, params=None):
    # Never send a token to a URL supplied by a provider response or user.
    if platform == "gumroad":
        if path not in {"user", "sales", "products"}:
            raise ProviderError("Desteklenmeyen veri isteği.")
        url = "https://api.gumroad.com/v2/" + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = None
    elif platform == "upwork":
        url = "https://api.upwork.com/graphql"
        body = json.dumps({"query": JOB_QUERY}).encode()
    else:
        raise ProviderError("Bu platform için otomatik API bağlantısı mevcut değil.")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "MexAy-Channel-Hub/3.0",
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=12) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ProviderError("Platform yanıtı çok büyük.")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ProviderError("Platform geçerli veri döndürmedi.")
        if data.get("success") is False or data.get("errors"):
            raise ProviderError("Platform erişimi reddetti. Anahtarın süresini ve okuma izinlerini kontrol edin.")
        return data
    except ProviderError:
        raise
    except Exception:
        # Provider exception URLs and response bodies can contain secrets/PII.
        raise ProviderError("Platforma erişilemedi. Anahtarın süresini, izinlerini ve bağlantıyı kontrol edin.") from None


def initialize(c):
    c.execute("""CREATE TABLE IF NOT EXISTS channel_connections (
        user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
        platform TEXT NOT NULL, encrypted_token TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '', last_synced_at TIMESTAMPTZ,
        cursor TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(user_id, platform))""")
    c.execute("""CREATE TABLE IF NOT EXISTS channel_orders (
        id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        platform TEXT NOT NULL, external_id TEXT NOT NULL, title TEXT NOT NULL,
        customer TEXT NOT NULL DEFAULT '', amount NUMERIC(14,2) NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD', status TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual', is_test BOOLEAN NOT NULL DEFAULT FALSE,
        due_date DATE, notes TEXT NOT NULL DEFAULT '',
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(user_id, platform, external_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS channel_products (
        user_id BIGINT REFERENCES users(id) ON DELETE CASCADE, external_id TEXT NOT NULL,
        name TEXT NOT NULL, price BIGINT NOT NULL, currency TEXT NOT NULL,
        url TEXT NOT NULL DEFAULT '', published BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY(user_id, external_id))""")
    # Remove credentials belonging to the retired integration; order history is retained.
    c.execute("DELETE FROM channel_connections WHERE platform='fiverr'")
    if c.execute("SELECT to_regclass('channel_mail_events') AS relation").fetchone()["relation"]:
        c.execute("DELETE FROM channel_mail_events WHERE platform='fiverr'")
    c.execute("CREATE INDEX IF NOT EXISTS idx_channel_orders_user ON channel_orders(user_id, occurred_at DESC)")


def validate_order(d):
    if not isinstance(d, dict):
        raise ValueError("Her kayıt bir nesne olmalı.")
    platform, status = d.get("platform"), d.get("status", "in_progress")
    if platform not in PLATFORMS or status not in STATUSES:
        raise ValueError("Platform veya durum geçersiz.")
    title = str(d.get("title", "")).strip()
    external_id = str(d.get("external_id", "")).strip()
    if not title or len(title) > 300 or not external_id or len(external_id) > 200:
        raise ValueError("Başlık ve platform sipariş numarası gerekli; başlık en fazla 300 karakter olmalı.")
    try:
        amount = Decimal(str(d.get("amount", "")))
        if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999") or amount != amount.quantize(Decimal("0.01")):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValueError("Tutar sıfır veya pozitif, en fazla iki ondalık basamaklı sayı olmalı.") from None
    currency = str(d.get("currency", "USD")).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Para birimi USD gibi üç harfli bir kod olmalı.")
    due = d.get("due_date") or None
    if due:
        import datetime
        try:
            datetime.date.fromisoformat(str(due))
        except ValueError:
            raise ValueError("Teslim tarihi YYYY-MM-DD biçiminde olmalı.") from None
    return dict(platform=platform, status=status, title=title, external_id=external_id,
                amount=amount, currency=currency, customer=str(d.get("customer", ""))[:200],
                notes=str(d.get("notes", ""))[:4000], due_date=due)


def save_manual(c, uid, order):
    existing = c.execute("SELECT source FROM channel_orders WHERE user_id=%s AND platform IN ('upwork','gumroad') AND platform=%s AND external_id=%s FOR UPDATE",
                         (uid, order["platform"], order["external_id"])).fetchone()
    if existing and existing["source"] != "manual":
        raise ValueError("API'den gelen kaydı elle değiştiremezsiniz.")
    return c.execute("""INSERT INTO channel_orders(user_id,platform,external_id,title,customer,amount,currency,status,due_date,notes)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(user_id,platform,external_id) DO UPDATE SET title=EXCLUDED.title,customer=EXCLUDED.customer,
        amount=EXCLUDED.amount,currency=EXCLUDED.currency,status=EXCLUDED.status,due_date=EXCLUDED.due_date,
        notes=EXCLUDED.notes,updated_at=NOW() RETURNING id""",
        (uid, order["platform"], order["external_id"], order["title"], order["customer"], order["amount"],
         order["currency"], order["status"], order["due_date"], order["notes"])).fetchone()["id"]


def register(app, db, auth_required, run_pipeline, profile_for):
    bp = Blueprint("channels", __name__)

    @bp.errorhandler(ProviderError)
    def provider_error(exc):
        return jsonify(error=str(exc)), 502

    @bp.get("/api/channels")
    def channels():
        if (e := auth_required()): return e
        with db() as c:
            connections = {r["platform"]: r for r in c.execute(
                "SELECT platform,label,last_synced_at,last_error FROM channel_connections WHERE user_id=%s", (session["user_id"],)).fetchall()}
            totals = c.execute("""SELECT currency,SUM(amount) AS amount,COUNT(*) AS count FROM channel_orders
                WHERE user_id=%s AND platform IN ('upwork','gumroad') AND status='completed' AND is_test=FALSE GROUP BY currency ORDER BY currency""", (session["user_id"],)).fetchall()
            stats = c.execute("""SELECT COUNT(*) AS orders,
                COUNT(*) FILTER(WHERE status IN ('lead','in_progress')) AS active,
                COUNT(*) FILTER(WHERE due_date<CURRENT_DATE AND status='in_progress') AS overdue
                FROM channel_orders WHERE user_id=%s AND platform IN ('upwork','gumroad') AND is_test=FALSE""", (session["user_id"],)).fetchone()
        result = []
        for platform, info in PLATFORMS.items():
            con = connections.get(platform)
            result.append(dict(platform=platform, **info, connected=bool(con),
                state=("attention" if con and con["last_error"] else "connected" if con else "not_connected"),
                label=con["label"] if con else "", last_synced_at=con["last_synced_at"] if con else None,
                last_error=con["last_error"] if con else ""))
        return jsonify(channels=result, totals=[dict(currency=r["currency"],amount=str(r["amount"]),count=r["count"]) for r in totals],
                       stats=stats, token_storage_ready=bool(os.environ.get("INTEGRATION_ENCRYPTION_KEY")))

    @bp.post("/api/channels/<platform>/connect")
    def connect(platform):
        if (e := auth_required()): return e
        if platform not in {"gumroad", "upwork"}: return jsonify(error="Bu platform manuel kayıt destekliyor."), 400
        d = request.get_json(silent=True) or {}
        token = d.get("token")
        if not isinstance(token, str) or not 10 <= len(token) <= 4096 or any(ch.isspace() for ch in token):
            return jsonify(error="Geçerli API erişim anahtarı gerekli."), 400
        encrypted = cipher().encrypt(token.encode()).decode()
        if platform == "gumroad":
            data = remote_json(platform, token, "user")
            label = str(data.get("user", {}).get("name", "Gumroad"))[:200]
            remote_json(platform, token, "sales")  # verify view_sales before storing
        else:
            data = remote_json(platform, token)
            if not isinstance(data.get("data", {}).get("marketplaceJobPostingsSearch"), dict):
                raise ProviderError("Upwork anahtarı ilan okuma iznine sahip değil.")
            label = "Upwork API"
        with db() as c:
            c.execute("""INSERT INTO channel_connections(user_id,platform,encrypted_token,label)
                VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,platform) DO UPDATE
                SET encrypted_token=EXCLUDED.encrypted_token,label=EXCLUDED.label,cursor='',last_error=''""",
                (session["user_id"], platform, encrypted, label))
        return jsonify(ok=True)

    @bp.delete("/api/channels/<platform>/connection")
    def disconnect(platform):
        if (e := auth_required()): return e
        with db() as c:
            c.execute("DELETE FROM channel_connections WHERE user_id=%s AND platform IN ('upwork','gumroad') AND platform=%s", (session["user_id"], platform))
        return jsonify(ok=True)

    @bp.post("/api/channels/<platform>/sync")
    def sync(platform):
        if (e := auth_required()): return e
        uid = session["user_id"]
        with db() as c:
            # Prevent overlapping synchronizations and disconnect races for this account.
            c.execute("SELECT pg_advisory_xact_lock(%s)", (uid,))
            con = c.execute("SELECT * FROM channel_connections WHERE user_id=%s AND platform IN ('upwork','gumroad') AND platform=%s FOR UPDATE", (uid, platform)).fetchone()
            if not con: return jsonify(error="Önce platform erişim anahtarını bağlayın."), 409
            try:
                token = cipher().decrypt(con["encrypted_token"].encode()).decode()
                count = 0
                cursor = ""
                if platform == "gumroad":
                    products = remote_json(platform, token, "products").get("products", [])
                    c.execute("DELETE FROM channel_products WHERE user_id=%s", (uid,))
                    for p in products:
                        url = str(p.get("short_url", ""))
                        if urllib.parse.urlparse(url).scheme != "https": url = ""
                        c.execute("INSERT INTO channel_products(user_id,external_id,name,price,currency,url,published) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                            (uid,str(p["id"]),str(p["name"])[:300],int(p["price"]),str(p.get("currency","usd")).upper(),url,bool(p.get("published"))))
                    # Continue a bounded page; a completed cycle restarts at newest so refunds are refreshed.
                    params = {"page_key": con["cursor"]} if con["cursor"] else {}
                    data = remote_json(platform, token, "sales", params)
                    for sale in data.get("sales", []):
                        state = "refunded" if sale.get("refunded") or sale.get("chargedback") else "partial_refund" if sale.get("partially_refunded") else "disputed" if sale.get("disputed") and not sale.get("dispute_won") else "completed"
                        # Gumroad's canonical price is USD cents, independent of buyer presentment.
                        amount = Decimal(str(sale["price"])) / 100
                        if not amount.is_finite() or amount < 0: raise ProviderError("Platform tutarı geçersiz.")
                        c.execute("""INSERT INTO channel_orders(user_id,platform,external_id,title,amount,currency,status,source,is_test,occurred_at)
                            VALUES(%s,'gumroad',%s,%s,%s,'USD',%s,'api',%s,%s)
                            ON CONFLICT(user_id,platform,external_id) DO UPDATE SET title=EXCLUDED.title,amount=EXCLUDED.amount,
                            currency='USD',status=EXCLUDED.status,source='api',is_test=EXCLUDED.is_test,updated_at=NOW()""",
                            (uid,str(sale["id"]),str(sale.get("product_name","Gumroad satış"))[:300],amount,state,bool(sale.get("is_test_purchase")),sale["created_at"]))
                        count += 1
                    cursor = str(data.get("next_page_key") or "")
                elif platform == "upwork":
                    data = remote_json(platform, token)
                    edges = (data.get("data", {}).get("marketplaceJobPostingsSearch") or {}).get("edges", [])
                    raw = []
                    for edge in edges[:100]:
                        node = edge["node"]
                        # Do not invent payment verification, eligibility or Connects costs.
                        raw.append({"id": node["id"], "title": node["title"], "description": node.get("description", ""),
                                    "skills": node.get("skills", []), "url": "https://www.upwork.com/jobs/" + urllib.parse.quote(node["ciphertext"],safe="~") if node.get("ciphertext") else ""})
                    from agent.pipeline import ROOT
                    cfg = json.loads((ROOT / "config.json").read_text())
                    settings = c.execute("SELECT * FROM settings WHERE user_id=%s", (uid,)).fetchone()
                    if settings:
                        cfg.update(min_hourly_rate_usd=settings["min_hourly"],min_fixed_budget_usd=settings["min_fixed"],keywords=settings["keywords"].split(","),exclude_keywords=settings["excludes"].split(","))
                    for job in run_pipeline(raw, config=cfg, profile=profile_for(c,uid)):
                        existing = c.execute("SELECT id FROM jobs WHERE user_id=%s AND platform IN ('upwork','gumroad') AND external_id=%s ORDER BY id LIMIT 1", (uid,str(job["id"]))).fetchone()
                        if existing:
                            c.execute("UPDATE jobs SET title=%s,url=%s,description=%s,score=%s,payload=%s,updated_at=NOW() WHERE id=%s",
                                (job["title"],job.get("url"),job["description"],job["score"],json.dumps(job),existing["id"]))
                        else:
                            c.execute("INSERT INTO jobs(user_id,external_id,title,url,description,score,status,payload) VALUES(%s,%s,%s,%s,%s,%s,'new',%s)",
                                (uid,str(job["id"]),job["title"],job.get("url"),job["description"],job["score"],json.dumps(job)))
                        count += 1
                else: return jsonify(error="Bu platform manuel takip destekliyor."), 400
                c.execute("UPDATE channel_connections SET last_synced_at=NOW(),cursor=%s,last_error='' WHERE user_id=%s AND platform IN ('upwork','gumroad') AND platform=%s", (cursor,uid,platform))
            except (InvalidToken, ProviderError, KeyError, ValueError, TypeError, AttributeError, psycopg.Error):
                c.rollback()
                c.execute("UPDATE channel_connections SET last_error=%s WHERE user_id=%s AND platform IN ('upwork','gumroad') AND platform=%s",
                    ("Senkronizasyon başarısız. Erişim anahtarı ve okuma izinlerini kontrol edin.",uid,platform))
                return jsonify(error="Senkronizasyon başarısız. Erişim anahtarı ve okuma izinlerini kontrol edin."), 502
        return jsonify(ok=True, processed=count, has_more=bool(cursor))

    @bp.get("/api/channel-orders")
    def orders():
        if (e := auth_required()): return e
        with db() as c:
            rows = c.execute("SELECT * FROM channel_orders WHERE user_id=%s AND platform IN ('upwork','gumroad') ORDER BY occurred_at DESC LIMIT 1000", (session["user_id"],)).fetchall()
            total = c.execute("SELECT COUNT(*) AS n FROM channel_orders WHERE user_id=%s AND platform IN ('upwork','gumroad')", (session["user_id"],)).fetchone()["n"]
        for r in rows: r["amount"] = str(r["amount"])
        return jsonify(orders=rows,total=total)

    @bp.post("/api/channel-orders/import")
    def import_orders():
        if (e := auth_required()): return e
        d = request.get_json(silent=True) or {}
        rows = d.get("orders")
        if isinstance(d.get("csv"),str):
            rows = list(csv.DictReader(io.StringIO(d["csv"])))
        if not isinstance(rows,list) or not 1 <= len(rows) <= 500:
            return jsonify(error="Bir işlemde 1–500 kayıt yükleyin."), 400
        try:
            valid = [validate_order(r) for r in rows]
            with db() as c:
                c.execute("SELECT pg_advisory_xact_lock(%s)", (session["user_id"],))
                for order in valid: save_manual(c, session["user_id"],order)
        except ValueError as exc: return jsonify(error=str(exc)), 400
        return jsonify(ok=True,processed=len(valid))

    @bp.patch("/api/channel-orders/<int:oid>")
    def update_order(oid):
        if (e := auth_required()): return e
        d = request.get_json(silent=True) or {}
        with db() as c:
            row = c.execute("SELECT * FROM channel_orders WHERE id=%s AND user_id=%s FOR UPDATE", (oid,session["user_id"])).fetchone()
            if not row: return jsonify(error="Kayıt bulunamadı."), 404
            if row["source"] != "manual": return jsonify(error="API kaydını platformda güncelleyin, ardından eşitleyin."), 409
            try:
                row.update({k:v for k,v in d.items() if k in {"status","notes","due_date"}})
                save_manual(c,session["user_id"],validate_order(row))
            except ValueError as exc: return jsonify(error=str(exc)), 400
        return jsonify(ok=True)

    @bp.get("/api/channel-products")
    def products():
        if (e := auth_required()): return e
        with db() as c:
            rows = c.execute("SELECT * FROM channel_products WHERE user_id=%s AND platform IN ('upwork','gumroad') ORDER BY name", (session["user_id"],)).fetchall()
        return jsonify(products=rows)

    @bp.get("/api/channel-orders/export")
    def export():
        if (e := auth_required()): return e
        fields = ["platform","external_id","title","customer","amount","currency","status","due_date","notes","source","occurred_at"]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(fields)
        with db() as c:
            rows = c.execute("SELECT * FROM channel_orders WHERE user_id=%s AND platform IN ('upwork','gumroad') ORDER BY occurred_at DESC", (session["user_id"],)).fetchall()
        for row in rows:
            cells = []
            for field in fields:
                v = str(row[field] if row[field] is not None else "")
                cells.append("'" + v if v.lstrip().startswith(("=","+","-","@")) else v)
            writer.writerow(cells)
        return Response("\ufeff"+output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=mexay-orders.csv"})

    app.register_blueprint(bp)
