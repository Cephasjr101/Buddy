"""Agent brain: LLM (OpenAI) when key present, else built-in intent parser.
Parses voice-note text into structured intents the platform can execute."""
import json
import os
import re
from datetime import datetime, timedelta

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

INTENTS = {
    "find_leads": r"(?:find|get|search\s+for)\s+(?:buyers?|customers?|leads?|shops?|stores?|businesses|importers?)\s+(?:in\s+([\w\s]+?))?$|find\s+(.{3,60}?)(?:\s+in\s+([\w\s]+))?$",
    "schedule_call": r"(?:call|phone|ring)\s+([\w\s.@+]{3,40}?)(?:\s+on|\s+at|\s+tomorrow|\s+today|$)|schedule\s+a?\s*call",
    "appointment": r"(?:book|schedule|arrange|fix)\s+(?:an?\s+)?(?:appointment|meeting|visit)\s*(?:with\s+([\w\s.]{3,40}?))?(?:\s+on|\s+at|\s+tomorrow|$)",
    "reminder": r"remind me(?:\s+to)?\s+(.{3,80}?)(?:\s+at\s+([\d:apmAPM ]+))?(?:\s+on)?(\s+tomorrow|\s+today|\s+\d{4}-\d{2}-\d{2})?$",
    "play_music": r"(?:play|put on|music\s+for)\s+([\w\s'&.-]{2,40})",
    "email": r"(?:send|write|compose|draft)\s+(?:an?\s+)?email\s+to\s+([\w.@]{3,60}?)(?:\s+(?:about|saying|that)\s+(.{3,200}))?$",
    "marketing": r"(?:create|write|make|generate)\s+(?:a?\s*)?(?:marketing\s+)?post\s*(?:about\s+(.{3,120}))?",
    "post_now": r"post\s+it|publish\s+now",
}


def _llm_parse(text: str) -> dict:
    if not OPENAI_KEY:
        raise RuntimeError("no llm")
    from openai import OpenAI
    c = OpenAI(api_key=OPENAI_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""Today is {today}. Parse the user's message into JSON intent.
Intents: schedule_call{{who,when}}, appointment{{with,when,title}},
reminder{{text,when}}, play_music{{query}}, email{{to,subject,body}},
marketing{{topic}}, post_now{{}}, none{{}}.
"when" must be ISO datetime or "today"/"tomorrow HH:MM" style, best guess.
Message: {text!r}
Return ONLY JSON."""
    r = c.chat.completions.create(model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
    return json.loads(r.choices[0].message.content)


def _rule_parse(text: str) -> dict:
    t = text.strip()
    low = t.lower()
    for intent, pat in INTENTS.items():
        m = re.search(pat, low)
        if not m:
            continue
        g = [x for x in m.groups() if x]
        when = None
        for x in g:
            if re.search(r"\d{1,2}[:.]\d{2}|tomorrow|today|am|pm", x):
                when = x.strip()
        if intent == "schedule_call":
            return {"intent": intent, "who": g[0].strip() if g else "", "when": when}
        if intent == "appointment":
            return {"intent": intent, "with": g[0].strip() if g else "", "when": when,
                    "title": t[:60]}
        if intent == "reminder":
            return {"intent": intent, "text": g[0].strip() if g else t, "when": when}
        if intent == "play_music":
            return {"intent": intent, "query": g[0].strip() if g else ""}
        if intent == "email":
            return {"intent": intent, "to": g[0].strip() if g else "",
                    "body": g[1].strip() if len(g) > 1 else ""}
        if intent == "marketing":
            return {"intent": intent, "topic": g[0].strip() if g else ""}
        return {"intent": intent}
    return {"intent": "none"}


def parse(text: str) -> dict:
    try:
        return _llm_parse(text)
    except Exception:
        return _rule_parse(text)


def draft_post(business: str, topic: str = "", tone: str = "friendly") -> str:
    """Marketing caption generator: LLM or template fallback."""
    if OPENAI_KEY:
        try:
            from openai import OpenAI
            c = OpenAI(api_key=OPENAI_KEY)
            r = c.chat.completions.create(model="gpt-4o-mini", messages=[
                {"role": "user", "content":
                 f"Write a short punchy social media marketing post for {business}"
                 + (f" about {topic}" if topic else "") +
                 ". Include 3-4 relevant hashtags. Max 60 words."}])
            return r.choices[0].message.content.strip()
        except Exception:
            pass
    t = topic or "our latest products"
    return (f"\ud83d\ude80 {business} — {t}!\n\nQuality you can trust, prices you\u2019ll love. "
            f"DM us or tap the link in bio to order today. \ud83d\udcf1\ud83d\ude9a\n\n"
            f"#ShopNow #{re.sub(r'[^A-Za-z]', '', business) or 'Deals'} #Accra #Ghana")
