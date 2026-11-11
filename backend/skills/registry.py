"""Skill registry - toggleable capabilities per agent.
Voice skills are powered by the local VoiceStudio engine when installed."""
from backend.services import voice

SKILLS = {
    "voice_clone":   {"label": "Voice cloning (VoiceStudio)", "needs": "voicestudio",
                      "ready": voice.local_voice_available},
    "stt":           {"label": "Voice-note transcription", "needs": "voicestudio|openai",
                      "ready": lambda: voice.local_voice_available() or bool(voice.OPENAI_KEY)},
    "tts":           {"label": "Agent voice replies", "needs": "voicestudio|openai",
                      "ready": lambda: voice.local_voice_available() or bool(voice.OPENAI_KEY)},
    "calls":         {"label": "Make calls (Twilio)", "needs": "twilio",
                      "ready": lambda: bool(voice.os.getenv("TWILIO_SID"))},
    "whatsapp":      {"label": "WhatsApp messaging", "needs": "whatsapp",
                      "ready": lambda: bool(voice.os.getenv("WHATSAPP_TOKEN"))},
    "social_posting":{"label": "Auto-post marketing (FB/IG)", "needs": "meta",
                      "ready": lambda: bool(voice.os.getenv("FACEBOOK_PAGE_TOKEN"))},
    "email":         {"label": "Send & draft emails", "needs": "smtp",
                      "ready": lambda: bool(voice.os.getenv("SMTP_HOST"))},
    "music":         {"label": "Play music", "needs": "none", "ready": lambda: True},
    "scheduler":     {"label": "Appointments & reminders", "needs": "none", "ready": lambda: True},
    "marketing":     {"label": "Marketing post generator", "needs": "none", "ready": lambda: True},
    "lead_finder":   {"label": "Find buyers & customers (Google Places / web)", "needs": "google_places|serpapi",
                      "ready": lambda: bool(voice.os.getenv("GOOGLE_PLACES_KEY") or voice.os.getenv("SERPAPI_KEY"))},
}


def default_skills() -> dict:
    return {k: SKILLS[k]["ready"]() for k in SKILLS}


def skills_status() -> dict:
    return {k: {"label": v["label"], "needs": v["needs"], "ready": v["ready"]()}
            for k, v in SKILLS.items()}
