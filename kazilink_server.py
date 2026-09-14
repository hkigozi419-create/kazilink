#!/usr/bin/env python3
"""
KaziLink - runnable full-stack MVP
Uses only Python standard-library modules + SQLite.
Start: python3 kazilink_server.py
Open: http://localhost:8080
"""
import json, os, re, secrets, sqlite3, hashlib, hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "kazilink.db")
PUBLIC = os.path.join(BASE, "public")
HOST = os.environ.get("KAZILINK_HOST", "127.0.0.1")
PORT = int(os.environ.get("KAZILINK_PORT", "8080"))
ADMIN_EMAIL = os.environ.get("KAZILINK_ADMIN_EMAIL", "admin@kazilink.local")
ADMIN_PASSWORD = os.environ.get("KAZILINK_ADMIN_PASSWORD", "KaziLink123!")

SESSIONS = {}

def now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def hash_pw(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return salt.hex() + ":" + dk.hex()

def check_pw(password, stored):
    try:
        salt, digest = stored.split(":")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 180000).hex()
        return hmac.compare_digest(test, digest)
    except Exception:
        return False

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      phone TEXT NOT NULL UNIQUE,
      email TEXT,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('customer','worker','admin')),
      location TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS worker_profiles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
      trade TEXT NOT NULL,
      skills TEXT DEFAULT '',
      experience INTEGER DEFAULT 0,
      description TEXT DEFAULT '',
      photo_url TEXT DEFAULT '',
      verified INTEGER DEFAULT 0,
      featured INTEGER DEFAULT 0,
      rating REAL DEFAULT 0,
      review_count INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      category TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT NOT NULL,
      location TEXT NOT NULL,
      budget TEXT DEFAULT '',
      job_date TEXT DEFAULT '',
      status TEXT DEFAULT 'open',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS applications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      worker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      message TEXT NOT NULL,
      status TEXT DEFAULT 'pending',
      created_at TEXT NOT NULL,
      UNIQUE(job_id, worker_id)
    );
    CREATE TABLE IF NOT EXISTS reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      worker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
      rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
      comment TEXT DEFAULT '',
      created_at TEXT NOT NULL
    );
    """)
    # Seed admin account only if it does not already exist.
    row = con.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if not row:
        con.execute(
            "INSERT INTO users(name,phone,email,password_hash,role,location,created_at) VALUES(?,?,?,?,?,?,?)",
            ("KaziLink Admin", "0000000000", ADMIN_EMAIL, hash_pw(ADMIN_PASSWORD), "admin", "Kampala", now())
        )
    # Seed demo workers if the database is empty.
    if con.execute("SELECT COUNT(*) c FROM worker_profiles").fetchone()["c"] == 0:
        demos = [
            ("Moses Aluminium", "+256700000001", "Aluminium Fabricator", "Windows, doors, shop fronts, partitions", 6, "Experienced aluminium fabricator and installer.", "Kampala"),
            ("Brian Auto", "+256700000002", "Vehicle Mechanic", "Starters, alternators, wiring, fuel pumps", 4, "Vehicle electrical and mechanical repairs.", "Kampala"),
            ("Sarah Electrical", "+256700000003", "Electrician", "House wiring, sockets, lighting", 5, "Domestic and commercial electrical work.", "Wakiso"),
            ("Peter Builder", "+256700000004", "Construction", "Block work, plastering, roofing", 7, "General construction and finishing.", "Kampala"),
            ("John Plumber", "+256700000005", "Plumber", "Pipes, drainage, water systems", 5, "Residential plumbing and repairs.", "Kira"),
        ]
        for name, phone, trade, skills, exp, desc, loc in demos:
            con.execute(
                "INSERT INTO users(name,phone,password_hash,role,location,created_at) VALUES(?,?,?,?,?,?)",
                (name, phone, hash_pw("Demo123!"), "worker", loc, now())
            )
            uid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.execute(
                "INSERT INTO worker_profiles(user_id,trade,skills,experience,description,verified,featured,rating,review_count) VALUES(?,?,?,?,?,?,?,?,?)",
                (uid, trade, skills, exp, desc, 1, 0, 4.8, 12)
            )
    con.commit()
    con.close()

def public_user(row):
    if not row: return None
    d = dict(row)
    d.pop("password_hash", None)
    return d

def worker_dict(row):
    d = dict(row)
    return d

def get_session_user(handler):
    token = handler.headers.get("Authorization", "").replace("Bearer ", "").strip()
    uid = SESSIONS.get(token)
    if not uid: return None
    con = db()
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    return public_user(row)

def require_user(handler, roles=None):
    u = get_session_user(handler)
    if not u:
        handler.send_json({"error":"Authentication required"}, 401)
        return None
    if roles and u["role"] not in roles:
        handler.send_json({"error":"Not authorized"}, 403)
        return None
    return u

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length","0"))
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode() or "{}")

    def serve_static(self, path):
        if path == "/": path = "/index.html"
        rel = os.path.normpath(path.lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel):
            self.send_error(404); return
        fp = os.path.join(PUBLIC, rel)
        if not os.path.isfile(fp):
            self.send_error(404); return
        types = {".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".json":"application/json"}
        ctype = types.get(os.path.splitext(fp)[1], "application/octet-stream")
        data = open(fp,"rb").read()
        self.send_response(200)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path)
        if not p.path.startswith("/api/"):
            return self.serve_static(p.path)
        con = db()
        try:
            if p.path == "/api/me":
                u = require_user(self)
                if u: self.send_json({"user":u})
                return
            if p.path == "/api/workers":
                q = parse_qs(p.query)
                trade = q.get("trade",[""])[0]
                location = q.get("location",[""])[0]
                sql = """SELECT u.id user_id,u.name,u.phone,u.location,wp.* FROM users u
                         JOIN worker_profiles wp ON wp.user_id=u.id WHERE u.role='worker'"""
                args=[]
                if trade:
                    sql += " AND lower(wp.trade) LIKE lower(?)"; args.append("%"+trade+"%")
                if location:
                    sql += " AND lower(u.location) LIKE lower(?)"; args.append("%"+location+"%")
                sql += " ORDER BY wp.verified DESC, wp.featured DESC, wp.rating DESC"
                rows = con.execute(sql,args).fetchall()
                self.send_json({"workers":[worker_dict(r) for r in rows]}); return
            if p.path.startswith("/api/workers/"):
                wid = p.path.rsplit("/",1)[1]
                row = con.execute("""SELECT u.id user_id,u.name,u.phone,u.email,u.location,
                                  wp.* FROM users u JOIN worker_profiles wp ON wp.user_id=u.id
                                  WHERE u.id=? AND u.role='worker'""",(wid,)).fetchone()
                if not row: self.send_json({"error":"Worker not found"},404); return
                reviews = con.execute("""SELECT r.rating,r.comment,r.created_at,u.name customer_name
                                         FROM reviews r JOIN users u ON u.id=r.customer_id
                                         WHERE r.worker_id=? ORDER BY r.id DESC""",(wid,)).fetchall()
                self.send_json({"worker":worker_dict(row),"reviews":[dict(x) for x in reviews]}); return
            if p.path == "/api/jobs":
                q = parse_qs(p.query); category=q.get("category",[""])[0]; location=q.get("location",[""])[0]
                sql="""SELECT j.*,u.name customer_name FROM jobs j JOIN users u ON u.id=j.customer_id
                       WHERE j.status='open'"""; args=[]
                if category: sql+=" AND lower(j.category) LIKE lower(?)"; args.append("%"+category+"%")
                if location: sql+=" AND lower(j.location) LIKE lower(?)"; args.append("%"+location+"%")
                sql+=" ORDER BY j.id DESC"
                self.send_json({"jobs":[dict(x) for x in con.execute(sql,args).fetchall()]}); return
            if p.path == "/api/applications":
                u=require_user(self,["worker","customer","admin"])
                if not u: return
                if u["role"]=="worker":
                    rows=con.execute("""SELECT a.*,j.title,j.category,j.location,j.budget,u.name customer_name
                                      FROM applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=j.customer_id
                                      WHERE a.worker_id=? ORDER BY a.id DESC""",(u["id"],)).fetchall()
                elif u["role"]=="customer":
                    rows=con.execute("""SELECT a.*,j.title,j.category,j.location,u.name worker_name
                                      FROM applications a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=a.worker_id
                                      WHERE j.customer_id=? ORDER BY a.id DESC""",(u["id"],)).fetchall()
                else:
                    rows=con.execute("""SELECT a.*,j.title,u.name worker_name FROM applications a
                                      JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=a.worker_id ORDER BY a.id DESC""").fetchall()
                self.send_json({"applications":[dict(x) for x in rows]}); return
            if p.path == "/api/admin/stats":
                u=require_user(self,["admin"])
                if not u:return
                stats={}
                for table in ["users","worker_profiles","jobs","applications","reviews"]:
                    stats[table]=con.execute("SELECT COUNT(*) c FROM "+table).fetchone()["c"]
                self.send_json(stats); return
            self.send_json({"error":"Not found"},404)
        finally:
            con.close()

    def do_POST(self):
        p=urlparse(self.path)
        try: data=self.read_json()
        except Exception:
            self.send_json({"error":"Invalid JSON"},400); return
        con=db()
        try:
            if p.path=="/api/register":
                name=str(data.get("name","")).strip(); phone=str(data.get("phone","")).strip()
                password=str(data.get("password","")); role=data.get("role","customer")
                location=str(data.get("location","")).strip()
                if not name or not phone or len(password)<6 or role not in ("customer","worker"):
                    self.send_json({"error":"Name, phone, role and password (6+ chars) are required"},400); return
                if con.execute("SELECT id FROM users WHERE phone=?",(phone,)).fetchone():
                    self.send_json({"error":"Phone already registered"},409); return
                con.execute("""INSERT INTO users(name,phone,email,password_hash,role,location,created_at)
                               VALUES(?,?,?,?,?,?,?)""",
                            (name,phone,data.get("email"),hash_pw(password),role,location,now()))
                uid=con.execute("SELECT last_insert_rowid()").fetchone()[0]
                if role=="worker":
                    trade=str(data.get("trade","")).strip()
                    if not trade:
                        self.send_json({"error":"Trade is required for workers"},400); con.rollback(); return
                    con.execute("""INSERT INTO worker_profiles(user_id,trade,skills,experience,description,photo_url)
                                   VALUES(?,?,?,?,?,?)""",
                                (uid,trade,str(data.get("skills","")),int(data.get("experience",0) or 0),
                                 str(data.get("description","")),str(data.get("photo_url",""))))
                con.commit()
                token=secrets.token_urlsafe(32); SESSIONS[token]=uid
                user=public_user(con.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone())
                self.send_json({"token":token,"user":user},201); return

            if p.path=="/api/login":
                identifier=str(data.get("identifier","")).strip(); password=str(data.get("password",""))
                row=con.execute("SELECT * FROM users WHERE phone=? OR email=?",(identifier,identifier)).fetchone()
                if not row or not check_pw(password,row["password_hash"]):
                    self.send_json({"error":"Invalid login details"},401); return
                token=secrets.token_urlsafe(32); SESSIONS[token]=row["id"]
                self.send_json({"token":token,"user":public_user(row)}); return

            if p.path=="/api/logout":
                token=self.headers.get("Authorization","").replace("Bearer ","").strip()
                SESSIONS.pop(token,None); self.send_json({"ok":True}); return

            if p.path=="/api/jobs":
                u=require_user(self,["customer"])
                if not u:return
                required=["category","title","description","location"]
                if any(not str(data.get(k,"")).strip() for k in required):
                    self.send_json({"error":"Category, title, description and location are required"},400); return
                con.execute("""INSERT INTO jobs(customer_id,category,title,description,location,budget,job_date,status,created_at)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                            (u["id"],data["category"],data["title"],data["description"],data["location"],
                             data.get("budget",""),data.get("job_date",""),"open",now()))
                con.commit()
                self.send_json({"job_id":con.execute("SELECT last_insert_rowid()").fetchone()[0]},201); return

            m=re.match(r"^/api/jobs/(\\d+)/apply$",p.path)
            if m:
                u=require_user(self,["worker"])
                if not u:return
                jid=int(m.group(1))
                if not con.execute("SELECT id FROM jobs WHERE id=? AND status='open'",(jid,)).fetchone():
                    self.send_json({"error":"Job not found or closed"},404); return
                try:
                    con.execute("INSERT INTO applications(job_id,worker_id,message,created_at) VALUES(?,?,?,?)",
                                (jid,u["id"],str(data.get("message","")).strip() or "I am interested in this job.",now()))
                    con.commit()
                except sqlite3.IntegrityError:
                    self.send_json({"error":"You already applied for this job"},409); return
                self.send_json({"ok":True},201); return

            if p.path=="/api/reviews":
                u=require_user(self,["customer"])
                if not u:return
                wid=int(data.get("worker_id")); rating=int(data.get("rating"))
                if rating<1 or rating>5:
                    self.send_json({"error":"Rating must be 1-5"},400); return
                if not con.execute("SELECT id FROM users WHERE id=? AND role='worker'",(wid,)).fetchone():
                    self.send_json({"error":"Worker not found"},404); return
                con.execute("""INSERT INTO reviews(customer_id,worker_id,job_id,rating,comment,created_at)
                               VALUES(?,?,?,?,?,?)""",
                            (u["id"],wid,data.get("job_id"),rating,str(data.get("comment","")),now()))
                agg=con.execute("SELECT AVG(rating) avg,COUNT(*) c FROM reviews WHERE worker_id=?",(wid,)).fetchone()
                con.execute("UPDATE worker_profiles SET rating=?,review_count=? WHERE user_id=?",
                            (round(agg["avg"],2),agg["c"],wid))
                con.commit(); self.send_json({"ok":True},201); return

            if p.path=="/api/admin/verify":
                u=require_user(self,["admin"])
                if not u:return
                wid=int(data.get("worker_id"))
                con.execute("UPDATE worker_profiles SET verified=? WHERE user_id=?",(1 if data.get("verified",True) else 0,wid))
                con.commit(); self.send_json({"ok":True}); return

            if p.path=="/api/admin/feature":
                u=require_user(self,["admin"])
                if not u:return
                wid=int(data.get("worker_id"))
                con.execute("UPDATE worker_profiles SET featured=? WHERE user_id=?",(1 if data.get("featured",True) else 0,wid))
                con.commit(); self.send_json({"ok":True}); return

            self.send_json({"error":"Not found"},404)
        finally:
            con.close()

if __name__=="__main__":
    init_db()
    print(f"KaziLink running at http://{HOST}:{PORT}")
    print(f"Admin login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
