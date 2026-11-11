"""AgentHub MVP - your named AI agents: voice notes in, calls, music,
appointments, reminders, email and daily marketing out.
Voice skills powered locally by VoiceStudio (github.com/debpalash/VoiceStudio)."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import urllib.parse
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from backend.security import (HttpsRedirectMiddleware, OriginCheckMiddleware,
                              RateLimiter, SecurityHeadersMiddleware, client_ip, limiter)
from backend.services import brain, integrations, leads, voice
from backend.skills.registry import default_skills, skills_status

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET = os.getenv("SHOP_SECRET", "dev-secret-change-me")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "agenthub.db"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AgentHub", debug=False, docs_url=None, redoc_url=None, openapi_url=None)
# security middleware order: HTTPS -> headers -> origin(CSRF) -> app
app.add_middleware(OriginCheckMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HttpsRedirectMiddleware)
sched = BackgroundScheduler()


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # never leak internals in production
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


# ------------------------------------------------------------------ database
def get_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
    finally:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.executescript(
        """CREATE TABLE IF NOT EXISTS users(
             id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
             password_hash TEXT NOT NULL, name TEXT DEFAULT '', phone TEXT DEFAULT '',
             is_admin INTEGER DEFAULT 0,
             created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS agents(
             id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
             name TEXT NOT NULL, role TEXT DEFAULT 'personal',
             personality TEXT DEFAULT '', business TEXT DEFAULT '',
             voice_id TEXT DEFAULT '', skills TEXT DEFAULT '{}',
             posts_per_day INTEGER DEFAULT 3, active INTEGER DEFAULT 1,
             created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS messages(
             id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
             user_id INTEGER NOT NULL, kind TEXT DEFAULT 'text',
             content TEXT, audio TEXT DEFAULT '', intent TEXT DEFAULT '{}',
             created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS tasks(
             id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER, user_id INTEGER,
             kind TEXT NOT NULL, payload TEXT DEFAULT '{}', status TEXT DEFAULT 'queued',
             result TEXT DEFAULT '', run_at TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS posts(
             id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL, user_id INTEGER,
             content TEXT, status TEXT DEFAULT 'draft', platform TEXT DEFAULT 'facebook',
             posted_at TEXT, created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS leads(
             id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
             agent_id INTEGER, source TEXT DEFAULT '', name TEXT DEFAULT '',
             phone TEXT DEFAULT '', address TEXT DEFAULT '', category TEXT DEFAULT '',
             city TEXT DEFAULT '', status TEXT DEFAULT 'new', notes TEXT DEFAULT '',
             created_at TEXT DEFAULT (datetime('now')));"""
    )
    if ADMIN_EMAIL and ADMIN_PASSWORD:
        db.execute("INSERT OR IGNORE INTO users(email,password_hash,name) VALUES(?,?,?)",
                   (ADMIN_EMAIL, _hash(ADMIN_PASSWORD), "Admin"))
        db.execute("UPDATE users SET is_admin=1 WHERE email=?", (ADMIN_EMAIL,))
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)")]
    if "is_admin" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    db.commit()
    db.close()
    try:
        os.chmod(DB_PATH, 0o600)   # only the service user can read the database
    except OSError:
        pass


def _hash(pw: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), b"agenthub", 60_000).hex()


# ---------------------------------------------------------------------- auth
COOKIE = "ah_token"
COOKIE_MAX = 60 * 60 * 24 * 14          # 14 days
RESET_MAX = 60 * 15                     # password-reset links expire in 15 min


def make_token(uid: int, purpose: str = "session") -> str:
    exp = timedelta(days=14) if purpose == "session" else timedelta(seconds=RESET_MAX)
    return jwt.encode({"uid": uid, "purpose": purpose,
                       "exp": datetime.utcnow() + exp}, SECRET, algorithm="HS256")


def _set_session(response, uid: int):
    """HttpOnly + Secure + SameSite=Strict cookie: unreadable by JS (XSS-safe),
    never sent cross-site (CSRF-safe)."""
    response.set_cookie(COOKIE, make_token(uid), max_age=COOKIE_MAX,
                        httponly=True, secure=True, samesite="strict", path="/")


def current_user(request: Request, db: sqlite3.Connection = Depends(get_db)):
    token = request.cookies.get(COOKIE) or ""
    if not token:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Sign in required")
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        if payload.get("purpose", "session") != "session":
            raise ValueError("wrong token type")
        uid = payload["uid"]
    except Exception:
        raise HTTPException(401, "Session expired")
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        raise HTTPException(401, "Account not found")
    return u


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(default="", max_length=30)
    age_consent: bool = False      # must affirm 16+
    terms_consent: bool = False    # must affirm Terms & Privacy


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _429(retry: int):
    return HTTPException(429, f"Too many attempts - try again in {retry}s")


@app.post("/api/auth/register")
def register(body: RegisterIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    retry = limiter.hit(f"reg:{client_ip(request)}", limit=3, window=600)
    if retry:
        raise _429(retry)
    if not body.age_consent:
        raise HTTPException(422, "You must confirm you are 16 or older")
    if not body.terms_consent:
        raise HTTPException(422, "You must agree to the Terms & Privacy Policy")
    if db.execute("SELECT 1 FROM users WHERE email=?", (body.email.lower(),)).fetchone():
        raise HTTPException(409, "Email already registered")
    cur = db.execute("INSERT INTO users(email,password_hash,name,phone) VALUES(?,?,?,?)",
                     (body.email.lower(), _hash(body.password), body.name, body.phone))
    db.commit()
    resp = JSONResponse({"name": body.name})
    _set_session(resp, cur.lastrowid)
    return resp


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    retry = limiter.hit(f"login:{client_ip(request)}:{body.email.lower()}", limit=5, window=300)
    if retry:
        raise _429(retry)
    u = db.execute("SELECT * FROM users WHERE email=?", (body.email.lower(),)).fetchone()
    if not u or not hmac.compare_digest(u["password_hash"], _hash(body.password)):
        raise HTTPException(401, "Wrong email or password")
    resp = JSONResponse({"name": u["name"], "is_admin": bool(u["is_admin"])})
    _set_session(resp, u["id"])
    return resp


@app.post("/api/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"name": user["name"], "email": user["email"], "is_admin": bool(user["is_admin"])}


class ForgotIn(BaseModel):
    email: EmailStr


@app.post("/api/auth/forgot-password")
def forgot(body: ForgotIn, request: Request, db: sqlite3.Connection = Depends(get_db)):
    retry = limiter.hit(f"forgot:{client_ip(request)}", limit=3, window=600)
    if retry:
        raise _429(retry)
    u = db.execute("SELECT * FROM users WHERE email=?", (body.email.lower(),)).fetchone()
    link = ""
    if u:
        token = make_token(u["id"], purpose="reset")
        link = f"{BASE_URL}/#/reset?token={token}"
        integrations.send_email(u["email"], "Password reset",
                                f"Reset your password within 15 minutes:\n{link}\n\nIf this wasn't you, ignore this email.")
    out = {"ok": True, "message": "If that email exists, a reset link is on its way (valid 15 min)."}
    if not integrations.SMTP_HOST:
        out["dev_link"] = link
    return out


class ResetIn(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=6)


@app.post("/api/auth/reset-password")
def reset(body: ResetIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        payload = jwt.decode(body.token, SECRET, algorithms=["HS256"])
        if payload.get("purpose") != "reset":
            raise ValueError("wrong type")
        uid = payload["uid"]
    except Exception:
        raise HTTPException(400, "Reset link is invalid or has expired - request a new one")
    if not db.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        raise HTTPException(400, "Account no longer exists")
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash(body.new_password), uid))
    db.commit()
    return {"ok": True, "message": "Password updated - sign in with your new password"}


class ChangePwIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


@app.post("/api/auth/change-password")
def change_pw(body: ChangePwIn, user=Depends(current_user),
              db: sqlite3.Connection = Depends(get_db)):
    if not hmac.compare_digest(user["password_hash"], _hash(body.current_password)):
        raise HTTPException(400, "Current password incorrect")
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash(body.new_password), user["id"]))
    db.commit()
    return {"ok": True}


class DeleteIn(BaseModel):
    password: str


@app.get("/api/export")
def export_data(user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    """Download everything we hold about you (data-access right, pairs with deletion)."""
    data = {"account": {"email": user["email"], "name": user["name"],
                        "phone": user["phone"], "created_at": user["created_at"]},
            "agents": [dict(r) for r in db.execute("SELECT * FROM agents WHERE user_id=?", (user["id"],)).fetchall()],
            "messages": [dict(r) for r in db.execute("SELECT * FROM messages WHERE user_id=?", (user["id"],)).fetchall()],
            "tasks": [dict(r) for r in db.execute("SELECT * FROM tasks WHERE user_id=?", (user["id"],)).fetchall()],
            "posts": [dict(r) for r in db.execute("SELECT * FROM posts WHERE user_id=?", (user["id"],)).fetchall()],
            "leads": [dict(r) for r in db.execute("SELECT * FROM leads WHERE user_id=?", (user["id"],)).fetchall()]}
    return JSONResponse(data, headers={"Content-Disposition": "attachment; filename=agenthub-export.json"})


@app.post("/api/auth/delete-account")
def delete_account(body: DeleteIn, user=Depends(current_user),
                   db: sqlite3.Connection = Depends(get_db)):
    if not hmac.compare_digest(user["password_hash"], _hash(body.password)):
        raise HTTPException(400, "Password incorrect - nothing deleted")
    for t in ("messages", "tasks", "posts"):
        db.execute(f"DELETE FROM {t} WHERE user_id=?", (user["id"],))
    db.execute("DELETE FROM agents WHERE user_id=?", (user["id"],))
    db.execute("DELETE FROM users WHERE id=?", (user["id"],))
    db.commit()
    return {"ok": True, "message": "Account and all agent data deleted"}


# --------------------------------------------------------------------- agents
class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    role: str = "personal"          # personal | business
    personality: str = Field(default="", max_length=300)
    business: str = Field(default="", max_length=120)
    posts_per_day: int = Field(default=3, ge=0, le=5)


@app.get("/api/agents")
def list_agents(user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM agents WHERE user_id=? AND active=1 ORDER BY id", (user["id"],)).fetchall()
    return {"agents": [dict(r) | {"skills": json.loads(r["skills"] or "{}")} for r in rows]}


@app.post("/api/agents")
def create_agent(body: AgentIn, user=Depends(current_user),
                 db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("INSERT INTO agents(user_id,name,role,personality,business,skills,posts_per_day)"
                     " VALUES(?,?,?,?,?,?,?)",
                     (user["id"], body.name, body.role, body.personality, body.business,
                      json.dumps(default_skills()), body.posts_per_day))
    db.commit()
    return {"id": cur.lastrowid}


class AgentUpdate(BaseModel):
    personality: str = ""
    business: str = ""
    posts_per_day: int = Field(default=3, ge=0, le=5)
    skills: dict = {}


@app.put("/api/agents/{aid}")
def update_agent(aid: int, body: AgentUpdate, user=Depends(current_user),
                 db: sqlite3.Connection = Depends(get_db)):
    a = _own_agent(aid, user, db)
    db.execute("UPDATE agents SET personality=?,business=?,posts_per_day=?,skills=? WHERE id=?",
               (body.personality, body.business, body.posts_per_day,
                json.dumps(body.skills or json.loads(a["skills"] or "{}")), aid))
    db.commit()
    return {"ok": True}


@app.delete("/api/agents/{aid}")
def delete_agent(aid: int, user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    _own_agent(aid, user, db)
    db.execute("UPDATE agents SET active=0 WHERE id=?", (aid,))
    db.commit()
    return {"ok": True}


def _own_agent(aid: int, user, db) -> sqlite3.Row:
    a = db.execute("SELECT * FROM agents WHERE id=? AND user_id=? AND active=1",
                   (aid, user["id"])).fetchone()
    if not a:
        raise HTTPException(404, "Agent not found")
    return a


@app.get("/api/skills")
def skills(user=Depends(current_user)):
    return {"skills": skills_status()}


@app.post("/api/agents/{aid}/clone-voice")
async def clone_voice(aid: int, sample: UploadFile = File(...),
                      user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    a = _own_agent(aid, user, db)
    ext = Path(sample.filename or "sample.wav").suffix[:6] or ".wav"
    path = os.path.join(UPLOAD_DIR, f"voice_{aid}{ext}")
    with open(path, "wb") as f:
        f.write(await sample.read())
    vid = voice.clone_voice(path, re.sub(r"\W+", "_", a["name"]))
    if not vid:
        raise HTTPException(503, "VoiceStudio not installed/configured (set VOICESTUDIO_DIR) and no OpenAI key")
    db.execute("UPDATE agents SET voice_id=? WHERE id=?", (vid, aid))
    db.commit()
    return {"voice_id": vid}


# ------------------------------------------------------------- chat / intents
def _reply(agent, text: str) -> str:
    name = agent["name"]
    persona = (agent["personality"] or "helpful and concise")
    if os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            c = OpenAI()
            r = c.chat.completions.create(model="gpt-4o-mini", messages=[
                {"role": "system", "content":
                 f"You are {name}, a {persona} assistant. Replies under 60 words."},
                {"role": "user", "content": text}])
            return r.choices[0].message.content.strip()
        except Exception:
            pass
    return f"Done - I handled that for you. (Add OPENAI_API_KEY for smarter {name} replies)"


def execute_intent(db, agent, user, parsed: dict) -> dict:
    """Run a parsed intent: create tasks/records + fire integrations."""
    intent = parsed.get("intent", "none")
    aid, uid = agent["id"], user["id"]
    out = {"intent": intent}

    if intent == "schedule_call":
        to = parsed.get("who", "")
        when = parsed.get("when", "")
        ok, msg = integrations.make_call(to, f"Hello, this is {agent['name']} calling on behalf of {user['name']}.")
        db.execute("INSERT INTO tasks(agent_id,user_id,kind,payload,status,result,run_at) VALUES(?,?,?,?,?,?,?)",
                   (aid, uid, "call", json.dumps({"to": to, "when": when}), "done" if ok else "queued", msg, _norm_when(when)))
        out["message"] = f"Call to {to} {'placed' if ok else 'queued'} " + (f"for {when}" if when else "")
    elif intent == "appointment":
        title = parsed.get("title") or "Appointment"
        when = _norm_when(parsed.get("when"))
        db.execute("INSERT INTO tasks(agent_id,user_id,kind,payload,status,result,run_at) VALUES(?,?,?,?,?,?,?)",
                   (aid, uid, "appointment", json.dumps({"with": parsed.get("with", ""), "title": title}),
                    "scheduled", "", when))
        out["message"] = f"Appointment '{title}' scheduled" + (f" for {when}" if when else "")
    elif intent == "reminder":
        when = _norm_when(parsed.get("when"))
        text = parsed.get("text", "")
        db.execute("INSERT INTO tasks(agent_id,user_id,kind,payload,status,result,run_at) VALUES(?,?,?,?,?,?,?)",
                   (aid, uid, "reminder", json.dumps({"text": text}), "scheduled", "", when))
        _schedule_reminder(db, aid, uid, text, when)
        out["message"] = f"Reminder set" + (f" for {when}" if when else "")
    elif intent == "play_music":
        q = parsed.get("query", "")
        link = integrations.music_link(q)
        db.execute("INSERT INTO tasks(agent_id,user_id,kind,payload,status,result) VALUES(?,?,?,?,?,?)",
                   (aid, uid, "music", json.dumps({"query": q}), "done", link))
        out["message"] = f"Playing '{q}'"
        out["link"] = link
    elif intent == "email":
        to = parsed.get("to", "")
        body = parsed.get("body", "")
        ok, msg = integrations.send_email(to, f"Message from {user['name']} via {agent['name']}", body)
        db.execute("INSERT INTO tasks(agent_id,user_id,kind,payload,status,result) VALUES(?,?,?,?,?,?)",
                   (aid, uid, "email", json.dumps({"to": to, "body": body}),
                    "sent" if ok else "draft", msg))
        out["message"] = f"Email to {to} {'sent' if ok else 'saved as draft'}"
    elif intent == "marketing":
        post = brain.draft_post(agent["business"] or f"{agent['name']}'s business",
                                parsed.get("topic", ""))
        db.execute("INSERT INTO posts(agent_id,user_id,content,status) VALUES(?,?,?,'draft')",
                   (aid, uid, post))
        out["message"] = "Marketing post drafted - see Posts tab"
        out["post"] = post
    elif intent == "post_now":
        _autopost(db, aid, uid, agent, force=True)
        out["message"] = "Posting now"
    elif intent == "find_leads":
        q = (parsed.get("what") or parsed.get("query") or "").strip()
        city = (parsed.get("city") or "").strip()
        ok, found, msg = leads.find("places", q or f"{agent['business'] or 'electronics'} shops", city)
        saved = 0
        for L in found:
            cur = db.execute(
                "INSERT OR IGNORE INTO leads(user_id,agent_id,source,name,phone,address,category,city)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (uid, aid, L["source"], L["name"], L["phone"], L["address"],
                 L.get("category", ""), city or L.get("city", "")))
            saved += cur.rowcount
        db.commit()
        out["message"] = f"Found {len(found)} leads, {saved} new saved" if ok else f"Lead search unavailable: {msg}"
        out["leads"] = len(found)
    else:
        out["message"] = _reply(agent, json.dumps(parsed))
    return out


def _norm_when(when) -> str:
    if not when:
        return None
    when = str(when).strip().lower()
    now = datetime.now()
    try:
        if "tomorrow" in when:
            d = now + timedelta(days=1)
            mt = re.search(r"(\d{1,2})[:.](\d{2})", when)
            return d.replace(hour=int(mt.group(1)) if mt else 9,
                             minute=int(mt.group(2)) if mt else 0,
                             second=0).strftime("%Y-%m-%d %H:%M")
        mt = re.search(r"(\d{4}-\d{2}-\d{2})[ T]?(\d{1,2}[:.]\d{2})?", when)
        if mt:
            return mt.group(1) + (" " + mt.group(2).replace(".", ":") if mt.group(2) else " 09:00")
        mt = re.search(r"(\d{1,2})[:.](\d{2})", when)
        if mt:
            return now.replace(hour=int(mt.group(1)), minute=int(mt.group(2)),
                               second=0).strftime("%Y-%m-%d %H:%M")
        return when
    except Exception:
        return None


def _schedule_reminder(db, aid, uid, text, when):
    if not when:
        return
    try:
        run_at = datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return
    if run_at < datetime.now():
        return
    def fire():
        d2 = sqlite3.connect(DB_PATH, check_same_thread=False)
        d2.execute("INSERT INTO tasks(agent_id,user_id,kind,payload,status,result) VALUES(?,?,?,?,?,?)",
                   (aid, uid, "reminder", json.dumps({"text": text}), "fired",
                    "REMINDER: " + text))
        d2.commit(); d2.close()
    sched.add_job(fire, DateTrigger(run_date=run_at), id=f"rem_{uuid.uuid4().hex[:8]}")


@app.get("/api/agents/{aid}/messages")
def messages(aid: int, user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    _own_agent(aid, user, db)
    rows = db.execute("SELECT * FROM messages WHERE agent_id=? ORDER BY id DESC LIMIT 100", (aid,)).fetchall()
    return {"messages": [dict(r) for r in reversed(rows)]}


class TextIn(BaseModel):
    text: str = Field(min_length=1)


@app.post("/api/agents/{aid}/text")
def chat_text(aid: int, body: TextIn, user=Depends(current_user),
              db: sqlite3.Connection = Depends(get_db)):
    agent = _own_agent(aid, user, db)
    db.execute("INSERT INTO messages(agent_id,user_id,kind,content) VALUES(?,?,'text',?)",
               (aid, user["id"], body.text))
    parsed = brain.parse(body.text)
    out = execute_intent(db, agent, user, parsed)
    db.execute("INSERT INTO messages(agent_id,user_id,kind,content,intent) VALUES(?,?,'agent',?,?)",
               (aid, user["id"], json.dumps(out), json.dumps(parsed)))
    db.commit()
    return out


@app.post("/api/agents/{aid}/voice")
async def chat_voice(aid: int, note: UploadFile = File(...),
                     user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    agent = _own_agent(aid, user, db)
    ext = Path(note.filename or "note.webm").suffix[:6] or ".webm"
    path = os.path.join(UPLOAD_DIR, f"note_{uuid.uuid4().hex[:8]}{ext}")
    with open(path, "wb") as f:
        f.write(await note.read())
    text = voice.transcribe(path)
    if not text:
        raise HTTPException(422, "Could not transcribe - check VoiceStudio/OpenAI config, or type instead")
    db.execute("INSERT INTO messages(agent_id,user_id,kind,content,audio) VALUES(?,?,'voice',?,?)",
               (aid, user["id"], text, path))
    parsed = brain.parse(text)
    out = execute_intent(db, agent, user, parsed)
    spoken = voice.speak(out.get("message", ""), agent["voice_id"]) if json.loads(agent["skills"] or "{}").get("tts", True) else ""
    db.execute("INSERT INTO messages(agent_id,user_id,kind,content,audio,intent) VALUES(?,?,'agent',?,?,?)",
               (aid, user["id"], json.dumps(out), spoken, json.dumps(parsed)))
    db.commit()
    return out | {"transcript": text, "audio": spoken.replace(UPLOAD_DIR, "/uploads") if spoken else ""}


# ------------------------------------------------------- records + marketing
@app.get("/api/tasks")
def tasks(user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM tasks WHERE user_id=? ORDER BY id DESC LIMIT 200",
                      (user["id"],)).fetchall()
    return {"tasks": [dict(r) | {"payload": json.loads(r["payload"] or "{}")} for r in rows]}


@app.get("/api/posts")
def posts(user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM posts WHERE user_id=? ORDER BY id DESC LIMIT 100",
                      (user["id"],)).fetchall()
    return {"posts": [dict(r) for r in rows]}


class PostIn(BaseModel):
    content: str = Field(min_length=2)


@app.post("/api/posts")
def create_post(body: PostIn, aid: int, user=Depends(current_user),
                db: sqlite3.Connection = Depends(get_db)):
    _own_agent(aid, user, db)
    cur = db.execute("INSERT INTO posts(agent_id,user_id,content,status) VALUES(?,?,?,'draft')",
                     (aid, user["id"], body.content))
    db.commit()
    return {"id": cur.lastrowid}


@app.post("/api/posts/{pid}/publish")
def publish_post(pid: int, user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    p = db.execute("SELECT * FROM posts WHERE id=? AND user_id=?", (pid, user["id"])).fetchone()
    if not p:
        raise HTTPException(404, "Post not found")
    agent = db.execute("SELECT * FROM agents WHERE id=?", (p["agent_id"],)).fetchone()
    ok_fb, rfb = integrations.post_to_facebook(p["content"])
    ok_ig, rig = integrations.post_to_instagram(p["content"])
    status = "posted" if ok_fb or ok_ig else "pending_token"
    db.execute("UPDATE posts SET status=?, posted_at=CASE WHEN ?='posted' THEN datetime('now') ELSE NULL END WHERE id=?",
               (status, status, pid))
    db.commit()
    return {"ok": ok_fb or ok_ig, "facebook": rfb, "instagram": rig, "status": status}


def _autopost(db, aid, uid, agent, force=False):
    p = brain.draft_post(agent["business"] or agent["name"])
    ok_fb, _ = integrations.post_to_facebook(p)
    ok_ig, _ = integrations.post_to_instagram(p)
    status = "posted" if ok_fb or ok_ig else "pending_token"
    db.execute("INSERT INTO posts(agent_id,user_id,content,status,posted_at) VALUES(?,?,?,?,CASE WHEN ?='posted' THEN datetime('now') ELSE NULL END)",
               (aid, uid, p, status, status))
    db.commit()


def marketing_tick():
    """Scheduler: for each business agent, spread posts_per_day across the day."""
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    for a in db.execute("SELECT * FROM agents WHERE active=1 AND role='business' AND posts_per_day>0").fetchall():
        done = db.execute("SELECT COUNT(*) n FROM posts WHERE agent_id=? AND date(posted_at)=date('now') AND status='posted'",
                          (a["id"],)).fetchone()["n"]
        if done < a["posts_per_day"]:
            _autopost(db, a["id"], a["user_id"], a)
    db.close()


# ---------------------------------------------------------------------- leads
class LeadFindIn(BaseModel):
    agent_id: int
    source: str = "places"          # places | web
    query: str = Field(min_length=2)
    city: str = ""


@app.post("/api/leads/find")
def leads_find(body: LeadFindIn, user=Depends(current_user),
               db: sqlite3.Connection = Depends(get_db)):
    _own_agent(body.agent_id, user, db)
    ok, found, msg = leads.find(body.source, body.query, body.city)
    saved = 0
    if ok:
        for L in found:
            cur = db.execute(
                "INSERT OR IGNORE INTO leads(user_id,agent_id,source,name,phone,address,category,city)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (user["id"], body.agent_id, L["source"], L["name"], L["phone"],
                 L["address"], L.get("category", ""), body.city or L.get("city", "")))
            saved += cur.rowcount
        db.commit()
    return {"ok": ok, "found": len(found), "saved_new": saved, "message": msg,
            "leads": found if ok else []}


@app.get("/api/leads")
def leads_list(user=Depends(current_user), db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM leads WHERE user_id=? ORDER BY id DESC LIMIT 500",
                      (user["id"],)).fetchall()
    return {"leads": [dict(r) for r in rows]}


class LeadUpdate(BaseModel):
    status: str = "new"             # new | contacted | qualified | converted | dead
    notes: str = ""


@app.put("/api/leads/{lid}")
def lead_update(lid: int, body: LeadUpdate, user=Depends(current_user),
                db: sqlite3.Connection = Depends(get_db)):
    if body.status not in ("new", "contacted", "qualified", "converted", "dead"):
        raise HTTPException(400, "Bad status")
    r = db.execute("UPDATE leads SET status=?, notes=? WHERE id=? AND user_id=?",
                   (body.status, body.notes[:300], lid, user["id"]))
    db.commit()
    if not r.rowcount:
        raise HTTPException(404, "Lead not found")
    return {"ok": True}


@app.post("/api/leads/{lid}/contact")
def lead_contact(lid: int, payload: dict, user=Depends(current_user),
                 db: sqlite3.Connection = Depends(get_db)):
    lead = db.execute("SELECT * FROM leads WHERE id=? AND user_id=?", (lid, user["id"])).fetchone()
    if not lead:
        raise HTTPException(404, "Lead not found")
    channel = str(payload.get("channel", "whatsapp"))
    if channel == "call":
        phone = lead["phone"] or payload.get("phone", "")
        ok, msg = integrations.make_call(phone, f"Hello, this is a quick call regarding our products.")
        db.execute("UPDATE leads SET status='contacted' WHERE id=?", (lid,))
        db.commit()
        return {"ok": ok, "message": msg}
    # whatsapp deep link (works without API keys)
    phone = re.sub(r"[^\d]", "", lead["phone"] or payload.get("phone", ""))
    link = f"https://wa.me/{phone}?text=" + urllib.parse.quote(
        f"Hello {lead['name']}, I found your business and would like to connect.")
    db.execute("UPDATE leads SET status='contacted' WHERE id=?", (lid,))
    db.commit()
    return {"ok": True, "link": link}


# --------------------------------------------------------------------- pages
@app.get("/api/health")
def health():
    return {"ok": True, "voice": voice.local_voice_available(),
            "llm": bool(os.getenv("OPENAI_API_KEY")), "time": datetime.utcnow().isoformat()}


app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend" / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith(("api/", "uploads/")):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return FileResponse(BASE_DIR / "frontend" / "static" / "index.html")


init_db()
if not sched.running:
    sched.add_job(marketing_tick, "interval", hours=4, id="mkt")
    sched.start()
