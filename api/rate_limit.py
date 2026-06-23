import os
import time
from collections import deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from api.security import decode_access_token


class InMemoryRateLimiter:
    """单进程内存限流器，适合本地 demo；多实例部署时应替换为 Redis。"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max(max_requests, 1)
        self.window_seconds = max(window_seconds, 1)
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        now = time.monotonic()
        window_start = now - self.window_seconds
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= window_start:
                hits.popleft()
            remaining = self.max_requests - len(hits)
            if remaining <= 0:
                retry_after = max(int(self.window_seconds - (now - hits[0])), 1)
                return False, 0, retry_after
            hits.append(now)
            return True, remaining - 1, 0


rate_limiter = InMemoryRateLimiter(
    max_requests=int(os.getenv("API_RATE_LIMIT_REQUESTS", "120")),
    window_seconds=int(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60")),
)


def _client_key(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            subject = payload.get("sub")
            if subject:
                return f"user:{subject}"
        except Exception:
            pass

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


async def rate_limit_middleware(request: Request, call_next) -> Response:
    if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
        return await call_next(request)

    allowed, remaining, retry_after = rate_limiter.check(_client_key(request))
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(rate_limiter.max_requests),
                "X-RateLimit-Remaining": "0",
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response
