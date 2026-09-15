#!/usr/bin/env python3
"""
KaziLink production MVP backend.
Persistent application data is stored in Supabase Postgres through its REST API.
The Supabase service-role key is read ONLY from the server environment and is
never sent to the browser.
"""
import json, os, re, secrets, hashlib, hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
HOST = os.environ.get("KAZILINK_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("KAZILINK_PORT", "8080")))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ADMIN_EMAIL = os.environ.get("KAZILINK_ADMIN_EMAIL", "admin@kazilink.local")
ADMIN_PASSWORD = os.environ.get("KAZILINK_ADMIN_PASSWORD", "KaziLink123!")
SESSIONS = {}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def sb_request(method, table, params=None, body=None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase server environment variables are not configured")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        parts=[]
        for k,v in params.items():
            parts.append(f"{k}={quote(str(v), safe='(),.*=')}")
        url += "?" + "&".join(parts)
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if method in ("POST", "PATCH", "DELETE"):
        headers["Prefer"] = "return=representation"
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as r:
            raw=r.read().decode()
            return json.loads(raw) if raw else []
    except HTTPError as e:
        msg=e.read().decode(errors="replace")
        raise RuntimeError(f"Supabase {e.code}: {msg}")
    except URLError as e:
        raise RuntimeError(f"Supabase connection error: {e}")


def one(table, params):
    rows=sb_request("GET", table, params)
    return rows[0] if rows else None


def public_user(row):
    if not row: return None
    return {k:v for k,v in row.items() if k != "password_hash"}


def get_session_user(handler):
    token=handler.headers.get("Authorization","").replace("Bearer ","").strip()
    uid=SESSIONS.get(token)
    if not uid: return None
    row=one("users", {"id":f"eq.{uid}", "select":"*"})
    return public_user(row)


def require_user(handler, roles=None):
    u=get_session_user(handler)
    if not u:
        handler.send_json({"error":"Authentication required"},401); return None
    if roles and u["role"] not in roles:
        handler.send_json({"error":"Not authorized"},403); return None
    return u


def worker_rows(trade="", location=""):
    users=sb_request("GET","users",{"select":"id,name,phone,email,role,location,created_at","role":"eq.worker","order":"created_at.desc"})
    profiles=sb_request("GET","worker_profiles",{"select":"*"})
    by={p["user_id"]:p for p in profiles}
    wt=trade.strip().lower(); wl=location.strip().lower()
    out=[]
    for u in users:
        p=by.get(u["id"])
        if not p: continue
        loc=str(u.get("location") or "").lower()
        tr=str(p.get("trade") or "").lower()
        if wl and wl not in loc and loc not in wl: continue
        if wt and wt not in tr and tr not in wt: continue
        d={**u,**p,"user_id":u["id"]}
        d["experience"]=p.get("experience",p.get("experience_years",0))
        out.append(d)
    out.sort(key=lambda x:(not bool(x.get("verified")),not bool(x.get("featured")),-float(x.get("rating") or 0)))
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args))
    def send_json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(body)
    def read_json(self):
        n=int(self.headers.get("Content-Length","0")); raw=self.rfile.read(n) if n else b"{}"; return json.loads(raw.decode() or "{}")
    def serve_static(self,path):
        if path=="/": path="/index.html"
        rel=os.path.normpath(path.lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel): self.send_error(404); return
        fp=os.path.join(PUBLIC,rel)
        if not os.path.isfile(fp): self.send_error(404); return
        types={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"application/javascript; charset=utf-8",".json":"application/json",".webmanifest":"application/manifest+json"}
        data=open(fp,"rb").read(); self.send_response(200); self.send_header("Content-Type",types.get(os.path.splitext(fp)[1],"application/octet-stream")); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        p=urlparse(self.path)
        if not p.path.startswith("/api/"): return self.serve_static(p.path)
        try:
            if p.path=="/api/me":
                u=require_user(self)
                if u:self.send_json({"user":u})
                return
            if p.path=="/api/workers":
                q=parse_qs(p.query); self.send_json({"workers":worker_rows(q.get("trade",[""])[0],q.get("location",[""])[0])}); return
            if p.path.startswith("/api/workers/"):
                wid=p.path.rsplit("/",1)[1]
                row=one("users",{"id":f"eq.{wid}","role":"eq.worker","select":"id,name,phone,email,location"})
                if not row:self.send_json({"error":"Worker not found"},404);return
                prof=one("worker_profiles",{"user_id":f"eq.{wid}","select":"*"})
                if not prof:self.send_json({"error":"Worker not found"},404);return
                reviews=sb_request("GET","reviews",{"worker_id":f"eq.{wid}","select":"rating,comment,created_at,customer_id","order":"created_at.desc"})
                for r in reviews:
                    cu=one("users",{"id":f"eq.{r['customer_id']}","select":"name"}); r["customer_name"]=cu.get("name") if cu else "Customer"
                d={**row,**prof,"user_id":wid,"experience":prof.get("experience",prof.get("experience_years",0))}
                self.send_json({"worker":d,"reviews":reviews});return
            if p.path=="/api/jobs":
                q=parse_qs(p.query); params={"select":"*","status":"eq.open","order":"created_at.desc"}
                rows=sb_request("GET","jobs",params); cat=q.get("category",[""])[0].lower(); loc=q.get("location",[""])[0].lower(); out=[]
                for j in rows:
                    if cat and cat not in str(j.get("category","")).lower():continue
                    if loc and loc not in str(j.get("location","")).lower():continue
                    cu=one("users",{"id":f"eq.{j['customer_id']}","select":"name"}); j["customer_name"]=cu.get("name") if cu else "Customer"; out.append(j)
                self.send_json({"jobs":out});return
            if p.path=="/api/applications":
                u=require_user(self,["worker","customer","admin"])
                if not u:return
                apps=sb_request("GET","applications",{"select":"*","order":"created_at.desc"}); out=[]
                for a in apps:
                    j=one("jobs",{"id":f"eq.{a['job_id']}","select":"*"})
                    if not j:continue
                    if u["role"]=="worker" and a["worker_id"]!=u["id"]:continue
                    if u["role"]=="customer" and j["customer_id"]!=u["id"]:continue
                    w=one("users",{"id":f"eq.{a['worker_id']}","select":"name"}); c=one("users",{"id":f"eq.{j['customer_id']}","select":"name"})
                    d={**a, "title":j.get("title",""),"category":j.get("category"),"location":j.get("location"),"budget":j.get("budget",""),"worker_name":w.get("name") if w else "Worker","customer_name":c.get("name") if c else "Customer"}; out.append(d)
                self.send_json({"applications":out});return
            if p.path=="/api/admin/stats":
                u=require_user(self,["admin"])
                if not u:return
                stats={}
                for t in ["users","worker_profiles","jobs","applications","reviews"]:
                    rows=sb_request("GET",t,{"select":"id"}); stats[t]=len(rows)
                self.send_json(stats);return
            self.send_json({"error":"Not found"},404)
        except Exception as e:
            print("GET error:",e); self.send_json({"error":"Server error","detail":str(e)},500)
    def do_POST(self):
        p=urlparse(self.path)
        try:data=self.read_json()
        except Exception:self.send_json({"error":"Invalid JSON"},400);return
        try:
            if p.path=="/api/register":
                name=str(data.get("name","")).strip(); phone=str(data.get("phone","")).strip(); password=str(data.get("password","")); role=data.get("role","customer"); location=str(data.get("location","")).strip()
                if not name or not phone or len(password)<6 or role not in ("customer","worker"):
                    self.send_json({"error":"Name, phone, role and password (6+ chars) are required"},400);return
                if one("users",{"phone":f"eq.{phone}","select":"id"}):self.send_json({"error":"Phone already registered"},409);return
                email=data.get("email")
                if email and one("users",{"email":f"eq.{email}","select":"id"}):self.send_json({"error":"Email already registered"},409);return
                u=sb_request("POST","users",{"select":"*"},{"name":name,"phone":phone,"email":email,"password_hash":hash_pw(password),"role":role,"location":location,"created_at":now()})[0]
                if role=="worker":
                    trade=str(data.get("trade","")).strip()
                    if not trade:self.send_json({"error":"Trade is required for workers"},400);return
                    sb_request("POST","worker_profiles",{"select":"*"},{"user_id":u["id"],"trade":trade,"skills":str(data.get("skills","")),"experience":int(data.get("experience",0) or 0),"description":str(data.get("description","")),"photo_url":str(data.get("photo_url",""))})
                token=secrets.token_urlsafe(32); SESSIONS[token]=u["id"]; self.send_json({"token":token,"user":public_user(u)},201);return
            if p.path=="/api/login":
                identifier=str(data.get("identifier","")).strip(); password=str(data.get("password",""))
                rows=sb_request("GET","users",{"or":f"(phone.eq.{identifier},email.eq.{identifier})","select":"*","limit":"1"})
                row=rows[0] if rows else None
                if not row or not check_pw(password,row.get("password_hash","")):self.send_json({"error":"Invalid login details"},401);return
                token=secrets.token_urlsafe(32);SESSIONS[token]=row["id"];self.send_json({"token":token,"user":public_user(row)});return
            if p.path=="/api/logout":
                token=self.headers.get("Authorization","").replace("Bearer ","").strip();SESSIONS.pop(token,None);self.send_json({"ok":True});return
            if p.path=="/api/jobs":
                u=require_user(self,["customer"])
                if not u:return
                required=["category","title","description","location"]
                if any(not str(data.get(k,"")).strip() for k in required):self.send_json({"error":"Category, title, description and location are required"},400);return
                j=sb_request("POST","jobs",{"select":"*"},{"customer_id":u["id"],"category":data["category"],"title":data["title"],"description":data["description"],"location":data["location"],"budget":data.get("budget",""),"job_date":data.get("job_date",""),"status":"open","created_at":now()})[0]
                self.send_json({"job_id":j["id"]},201);return
            m=re.match(r"^/api/jobs/(\d+)/apply$",p.path)
            if m:
                u=require_user(self,["worker"])
                if not u:return
                jid=int(m.group(1)); j=one("jobs",{"id":f"eq.{jid}","status":"eq.open","select":"id"})
                if not j:self.send_json({"error":"Job not found or closed"},404);return
                if one("applications",{"job_id":f"eq.{jid}","worker_id":f"eq.{u['id']}","select":"id"}):self.send_json({"error":"You already applied for this job"},409);return
                sb_request("POST","applications",{"select":"*"},{"job_id":jid,"worker_id":u["id"],"message":str(data.get("message","")).strip() or "I am interested in this job.","status":"pending","created_at":now()});self.send_json({"ok":True},201);return
            if p.path=="/api/reviews":
                u=require_user(self,["customer"])
                if not u:return
                wid=int(data.get("worker_id")); rating=int(data.get("rating"))
                if rating<1 or rating>5:self.send_json({"error":"Rating must be 1-5"},400);return
                if not one("users",{"id":f"eq.{wid}","role":"eq.worker","select":"id"}):self.send_json({"error":"Worker not found"},404);return
                sb_request("POST","reviews",{"select":"*"},{"customer_id":u["id"],"worker_id":wid,"job_id":data.get("job_id"),"rating":rating,"comment":str(data.get("comment","")),"created_at":now()})
                rs=sb_request("GET","reviews",{"worker_id":f"eq.{wid}","select":"rating"}); avg=round(sum(int(x["rating"]) for x in rs)/len(rs),2) if rs else 0
                sb_request("PATCH","worker_profiles",{"user_id":f"eq.{wid}"},{"rating":avg,"review_count":len(rs)});self.send_json({"ok":True},201);return
            if p.path=="/api/admin/verify":
                u=require_user(self,["admin"])
                if not u:return
                wid=int(data.get("worker_id"));sb_request("PATCH","worker_profiles",{"user_id":f"eq.{wid}"},{"verified":bool(data.get("verified",True))});self.send_json({"ok":True});return
            if p.path=="/api/admin/feature":
                u=require_user(self,["admin"])
                if not u:return
                wid=int(data.get("worker_id"));sb_request("PATCH","worker_profiles",{"user_id":f"eq.{wid}"},{"featured":bool(data.get("featured",True))});self.send_json({"ok":True});return
            self.send_json({"error":"Not found"},404)
        except Exception as e:
            print("POST error:",e);self.send_json({"error":"Server error","detail":str(e)},500)

if __name__=="__main__":
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the server environment.")
        raise SystemExit(1)
    print(f"KaziLink Supabase backend running on port {PORT}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
