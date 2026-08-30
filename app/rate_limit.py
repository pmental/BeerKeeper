import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# In-memory, single-process limiter - fine for how this app actually runs
# (one uvicorn process, no external worker pool), and avoids pulling in a
# dependency (e.g. Redis) for something this app doesn't otherwise need.
# Resets on restart, and doesn't share state across multiple processes if
# ever run that way - a reasonable trade-off for a self-hosted instance,
# not a substitute for one if this app is ever scaled out.
_buckets: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Deliberately just the direct connecting IP, not X-Forwarded-For:
    # trusting that header without knowing for certain a reverse proxy is
    # both in front of this app AND stripping/overwriting any client-
    # supplied value would let anyone bypass the limit by sending a
    # different fake IP on every request. If this is behind a proxy, every
    # request will share one bucket (the proxy's IP) unless that proxy is
    # configured to connect with the real client IP itself.
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, bucket_name: str, max_attempts: int, window_seconds: int) -> None:
    """Raises 429 if this IP has made more than max_attempts requests to
    this bucket within the trailing window_seconds. Call near the top of
    a route, before any expensive work (password hashing, sending email)."""
    key = f"{bucket_name}:{_client_ip(request)}"
    now = time.monotonic()
    bucket = _buckets[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= max_attempts:
        retry_after = int(window_seconds - (now - bucket[0])) + 1
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.append(now)
