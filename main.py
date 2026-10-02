import base64, hashlib, hmac, json, os, re, threading, time, uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from config import DB, DEMO_MODE, GEMINI_API_KEY, ORIGINS, SECRET
from services.gemini_service import generate

app = FastAPI(title="PocketSmart AI")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])
_lock = threading.Lock()

@app.middleware("http")
async def normalize_api_prefix(request, call_next):
    if request.scope["path"].startswith("/api/"):
        request.scope["path"] = request.scope["path"][4:]
    return await call_next(request)

def load():
    if not DB.exists(): return {"users": [], "recs": [], "revoked": []}
    return json.loads(DB.read_text())
def save(db): DB.parent.mkdir(exist_ok=True); DB.write_text(json.dumps(db))

def hash_pw(p, salt=None):
    salt = salt or os.urandom(16).hex()
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), 100_000).hex()
def make_token(uid):
    body = base64.urlsafe_b64encode(json.dumps({"uid": uid, "exp": time.time() + 7 * 86400, "jti": uuid.uuid4().hex}).encode()).decode()
    return body + "." + hmac.new(SECRET.encode(), body.encode(), "sha256").hexdigest()
def parse_token(t):
    try:
        body, sig = t.split(".")
        if not hmac.compare_digest(sig, hmac.new(SECRET.encode(), body.encode(), "sha256").hexdigest()): return None
        p = json.loads(base64.urlsafe_b64decode(body))
        return p if p["exp"] > time.time() else None
    except Exception: return None

def current(authorization: Optional[str] = Header(None)):
    p = parse_token((authorization or "").replace("Bearer ", ""))
    db = load()
    u = next((x for x in db["users"] if p and x["id"] == p["uid"]), None)
    if not u or p["jti"] in db["revoked"]: raise HTTPException(401, "Please log in to continue.")
    return {**u, "jti": p["jti"]}
def public(u): return {"id": u["id"], "name": u["name"], "email": u["email"]}

class Reg(BaseModel): name: str; email: str; password: str
class Login(BaseModel): email: str; password: str

@app.get("/health")
def health(): return {"status": "ok", "demo_mode": DEMO_MODE or not GEMINI_API_KEY}

@app.get("/api/health")
def health_api(): return health()

@app.post("/register")
def register(b: Reg):
    email = b.email.strip().lower()
    if not b.name.strip(): raise HTTPException(400, "Please enter your full name.")
    if not re.match(r"^\S+@\S+\.\S+$", email): raise HTTPException(400, "Please enter a valid email.")
    if len(b.password) < 6: raise HTTPException(400, "Password must be at least 6 characters.")
    with _lock:
        db = load()
        if any(u["email"] == email for u in db["users"]): raise HTTPException(409, "An account with this email already exists.")
        u = {"id": uuid.uuid4().hex, "name": b.name.strip(), "email": email, "password_hash": hash_pw(b.password)}
        db["users"].append(u); save(db)
    return {"user": public(u)}

@app.post("/login")
def login(b: Login):
    email = b.email.strip().lower()
    password = b.password
    db = load()
    u = next((x for x in db["users"] if x["email"] == email), None)

    if u is None and email == "demo@pocketsmart.ai" and password == "demo123":
        with _lock:
            db = load()
            if not any(x["email"] == email for x in db["users"]):
                u = {"id": uuid.uuid4().hex, "name": "Demo User", "email": email, "password_hash": hash_pw(password)}
                db["users"].append(u)
                save(db)
        u = next((x for x in load()["users"] if x["email"] == email), None)

    if not u or not hmac.compare_digest(hash_pw(password, u["password_hash"].split("$")[0]), u["password_hash"]):
        if not u:
            raise HTTPException(401, "Account not found. Create an account or use the demo login: demo@pocketsmart.ai / demo123.")
        raise HTTPException(401, "Incorrect email or password.")
    return {"token": make_token(u["id"]), "user": public(u)}

@app.post("/api/register")
def api_register(b: Reg): return register(b)

@app.post("/api/login")
def api_login(b: Login): return login(b)

@app.post("/logout")
def logout(u=Depends(current)):
    with _lock:
        db = load(); db["revoked"].append(u["jti"]); save(db)
    return {"ok": True}

@app.get("/session-info")
def session_info(u=Depends(current)): return {"user": public(u), "demo_mode": DEMO_MODE or not GEMINI_API_KEY}

def mine(u, kind=None):
    r = [x for x in load()["recs"] if x["user_id"] == u["id"] and (not kind or x["planner_type"] == kind)]
    return sorted(r, key=lambda x: x["created_at"], reverse=True)

@app.get("/session-data")
def session_data(u=Depends(current)):
    r = mine(u)
    return {"total": len(r), "saved": sum(1 for x in r if x.get("saved")), "recent": r[:3]}

def positive(v, msg):
    try: v = float(v)
    except (TypeError, ValueError): raise HTTPException(400, msg)
    if v <= 0: raise HTTPException(400, msg)
    return v

def run(kind, d, u):
    d["budget"] = positive(d.get("budget"), "Please enter a valid budget.")
    if kind == "party": d["guests"] = int(positive(d.get("guests"), "Please enter the number of guests."))
    if kind == "home" and d.get("room_quantity") is not None: d["room_quantity"] = int(positive(d["room_quantity"], "Please enter a valid room quantity."))
    if d.get("image"):
        if d.get("image_mime") not in ("image/jpeg", "image/png", "image/webp"): raise HTTPException(400, "Please upload a JPG, PNG or WebP image.")
        if len(d["image"]) > 6_000_000: raise HTTPException(400, "Image is too large. Please use one under 4 MB.")
    try: result = generate(kind, d)
    except RuntimeError as e: raise HTTPException(502, str(e))
    stored = {k: v for k, v in d.items() if k not in ("image", "force_demo")}
    stored["has_image"] = bool(d.get("image"))
    rec = {"id": uuid.uuid4().hex[:10], "user_id": u["id"], "planner_type": kind, "budget": d["budget"], "input_data": stored,
           "result": result, "saved": False, "created_at": datetime.now(timezone.utc).isoformat()}
    with _lock:
        db = load(); db["recs"].append(rec); save(db)
    return rec

@app.post("/generate-home")
def gen_home(d: dict, u=Depends(current)): return run("home", d, u)
@app.post("/generate-party")
def gen_party(d: dict, u=Depends(current)): return run("party", d, u)
@app.post("/generate-jewelry")
def gen_jewelry(d: dict, u=Depends(current)): return run("jewelry", d, u)

@app.get("/history")
def history(type: Optional[str] = None, u=Depends(current)): return {"items": mine(u, type)}

@app.get("/recommendations-details/{rid}")
def details(rid: str, u=Depends(current)):
    r = next((x for x in mine(u) if x["id"] == rid), None)
    if not r: raise HTTPException(404, "Recommendation not found.")
    return r

@app.post("/recommendations/{rid}/save")
def toggle_save(rid: str, u=Depends(current)):
    with _lock:
        db = load()
        r = next((x for x in db["recs"] if x["id"] == rid and x["user_id"] == u["id"]), None)
        if not r: raise HTTPException(404, "Recommendation not found.")
        r["saved"] = not r.get("saved"); save(db)
    return {"saved": r["saved"]}
