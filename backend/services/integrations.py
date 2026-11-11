"""Integration adapters: calls, WhatsApp, social posting, email.
Every adapter is env-gated and returns (ok, message) so the app never breaks
when a key is missing - tasks are queued instead."""
import os
import smtplib
from email.message import EmailMessage

import httpx

TW_SID = os.getenv("TWILIO_SID", "")
TW_TOKEN = os.getenv("TWILIO_TOKEN", "")
TW_FROM = os.getenv("TWILIO_FROM", "")
WA_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE = os.getenv("WHATSAPP_PHONE_ID", "")
FB_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "")
IG_ID = os.getenv("INSTAGRAM_BUSINESS_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def make_call(to: str, say_text: str, agent_voice_url: str = "") -> tuple[bool, str]:
    """Twilio call with agent TTS greeting. Queued task when unconfigured."""
    if not (TW_SID and TW_TOKEN and TW_FROM):
        return False, "Twilio not configured - call queued as task"
    twiml = f"<Response><Say voice='Polly.Joanna'>{say_text}</Say></Response>"
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{TW_SID}/Calls.json",
                   auth=(TW_SID, TW_TOKEN),
                   data={"To": to, "From": TW_FROM, "Twiml": twiml}, timeout=30)
    return (r.status_code < 300), (r.json().get("sid") if r.status_code < 300 else r.text[:200])


def whatsapp_send(to: str, text: str) -> tuple[bool, str]:
    if not (WA_TOKEN and WA_PHONE):
        return False, "WhatsApp API not configured"
    r = httpx.post(f"https://graph.facebook.com/v19.0/{WA_PHONE}/messages",
                   headers={"Authorization": f"Bearer {WA_TOKEN}"},
                   json={"messaging_product": "whatsapp", "to": to,
                         "type": "text", "text": {"body": text}}, timeout=30)
    return (r.status_code < 300), r.text[:200]


def post_to_facebook(text: str) -> tuple[bool, str]:
    if not FB_TOKEN:
        return False, "Facebook token not configured"
    r = httpx.post("https://graph.facebook.com/me/feed",
                   params={"access_token": FB_TOKEN, "message": text}, timeout=30)
    return (r.status_code < 300), (str(r.json().get("id")) if r.status_code < 300 else r.text[:200])


def post_to_instagram(text: str, image_url: str = "") -> tuple[bool, str]:
    if not (FB_TOKEN and IG_ID):
        return False, "Instagram not configured"
    if not image_url:
        return False, "Instagram posts need an image URL"
    c = httpx.post(f"https://graph.facebook.com/v19.0/{IG_ID}/media",
                   params={"access_token": FB_TOKEN, "image_url": image_url,
                           "caption": text}, timeout=30)
    if c.status_code >= 300:
        return False, c.text[:200]
    pub = httpx.post(f"https://graph.facebook.com/v19.0/{IG_ID}/media_publish",
                     params={"access_token": FB_TOKEN,
                             "creation_id": c.json()["id"]}, timeout=30)
    return (pub.status_code < 300), pub.text[:200]


def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return False, "SMTP not configured - email saved as draft"
    try:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = SMTP_FROM, to, subject
        m.set_content(body + "\n\n---\nYou received this because your contact was given to "
                       + (os.getenv("BASE_URL") or "our platform")
                       + ". Reply STOP to opt out, or manage everything in your account settings.")
        with smtplib.SMTP(SMTP_HOST, 587) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS); s.send_message(m)
        return True, "sent"
    except Exception as exc:
        return False, str(exc)[:200]


def music_link(query: str) -> str:
    """No API needed: deep link to YouTube music search (or Spotify if user adds)."""
    q = httpx.QueryParams({"search_query": query})
    return f"https://music.youtube.com/search?q={query.replace(' ', '+')}"
