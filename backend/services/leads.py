"""Lead finder: Google Places + SerpAPI web search -> normalized lead lists.
Env-gated: GOOGLE_PLACES_KEY / SERPAPI_KEY. Without keys, returns (False, msg)."""
import os
import re

import httpx

PLACES_KEY = os.getenv("GOOGLE_PLACES_KEY", "")
SERP_KEY = os.getenv("SERPAPI_KEY", "")


def places_leads(query: str, city: str = "", limit: int = 20) -> tuple[bool, list, str]:
    """e.g. query='phone accessory shops', city='Kumasi' -> businesses w/ phones."""
    if not PLACES_KEY:
        return False, [], "GOOGLE_PLACES_KEY not set - add it to fly secrets"
    q = f"{query} in {city}" if city else query
    r = httpx.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                  params={"query": q, "key": PLACES_KEY}, timeout=30)
    data = r.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return False, [], f"Places API: {data.get('status')} {data.get('error_message', '')[:120]}"
    out = []
    for p in (data.get("results") or [])[:limit]:
        out.append({
            "source": "google_places",
            "name": p.get("name", ""),
            "address": p.get("formatted_address", ""),
            "city": city,
            "phone": "",           # text search omits phone - enrich via details if needed
            "category": ", ".join(p.get("types", [])[:2]),
            "rating": p.get("rating", 0),
        })
    return True, out, "ok"


def web_leads(query: str, limit: int = 10) -> tuple[bool, list, str]:
    """SerpAPI organic results -> companies mentioning phones/contacts."""
    if not SERP_KEY:
        return False, [], "SERPAPI_KEY not set - add it to fly secrets"
    r = httpx.get("https://serpapi.com/search.json",
                  params={"engine": "google", "q": query, "api_key": SERP_KEY,
                          "num": limit, "gl": "gh"}, timeout=30)
    data = r.json()
    out = []
    phone_re = re.compile(r"\+?\d[\d\s\-]{8,14}")
    for item in (data.get("organic_results") or [])[:limit]:
        snippet = item.get("snippet", "") or ""
        m = phone_re.search(snippet)
        out.append({
            "source": "web_search",
            "name": (item.get("title") or "").split("|")[0].strip()[:80],
            "address": item.get("link", ""),
            "city": "",
            "phone": m.group(0).strip() if m else "",
            "category": query[:60],
            "rating": 0,
        })
    return True, out, "ok"


def find(source: str, query: str, city: str = "") -> tuple[bool, list, str]:
    if source == "places":
        return places_leads(query, city)
    return web_leads(query)
