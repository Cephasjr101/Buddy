"""Security middleware & helpers: rate limiting, hardened headers,
origin check (CSRF defense for cookie auth), HTTPS redirect."""
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


class RateLimiter:
    """In-memory sliding-window limiter. Production multi-instance: swap for
    Redis-backed (same interface)."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> int:
        """Returns seconds until retry allowed, or 0 if allowed."""
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return int(q[0] + window - now) + 1
            q.append(now)
            if len(self._hits) > 50_000:
                self._hits.clear()
            return 0


limiter = RateLimiter()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; media-src 'self' blob: https:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        return resp


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF defense: block cross-origin mutations (cookies are SameSite=Strict
    too - this is defense in depth for older browsers)."""

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin", "")
            if origin:
                host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
                if not origin.split("://", 1)[-1].split(":")[0].lower() == host.split(":")[0].lower():
                    return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
        return await call_next(request)


class HttpsRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "http" and request.url.path != "/api/health":
            url = request.url.replace(scheme="https")
            return RedirectResponse(str(url))
        return await call_next(request)


def client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.client.host if request.client else "unknown")
