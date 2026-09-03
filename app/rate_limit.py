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

# Each bucket self-trims its own old timestamps whenever it's accessed,
# but a bucket that's never revisited again (a one-off IP, a typo'd
# email) would otherwise sit in the dict forever, growing it without
# bound. _STALE_AFTER_SECONDS is deliberately much longer than any
# window_seconds this app actually uses (the longest today is 600s), so
# this can safely use one flat threshold instead of tracking each
# bucket's own window. Runs opportunistically, piggybacking on whichever
# request happens to land more than _CLEANUP_INTERVAL_SECONDS after the
# last sweep, rather than a dedicated background thread.
_last_cleanup = 0.0
_CLEANUP_INTERVAL_SECONDS = 600
_STALE_AFTER_SECONDS = 3600


def _cleanup_stale_buckets(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < _CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup = now
    stale_keys = [k for k, bucket in _buckets.items() if not bucket or now - bucket[-1] > _STALE_AFTER_SECONDS]
    for k in stale_keys:
        del _buckets[k]


def _client_ip(request: Request) -> str:
    # Deliberately just the direct connecting IP, not X-Forwarded-For:
    # trusting that header without knowing for certain a reverse proxy is
    # both in front of this app AND stripping/overwriting any client-
    # supplied value would let anyone bypass the limit by sending a
    # different fake IP on every request. If this is behind a proxy, every
    # request will share one bucket (the proxy's IP) unless that proxy is
    # configured to connect with the real client IP itself.
    return request.client.host if request.client else "unknown"


def _check_and_record(key: str, max_attempts: int, window_seconds: int) -> None:
    """Shared sliding-window logic for both rate_limit() (keyed by IP)
    and rate_limit_by_key() (keyed by anything else, e.g. an email
    address)."""
    now = time.monotonic()
    _cleanup_stale_buckets(now)
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


def rate_limit(request: Request, bucket_name: str, max_attempts: int, window_seconds: int) -> None:
    """Raises 429 if this IP has made more than max_attempts requests to
    this bucket within the trailing window_seconds. Call near the top of
    a route, before any expensive work (password hashing, sending email).
    """
    key = f"{bucket_name}:{_client_ip(request)}"
    _check_and_record(key, max_attempts, window_seconds)


def rate_limit_by_key(bucket_name: str, identity: str, max_attempts: int, window_seconds: int) -> None:
    """Same idea as rate_limit(), but keyed by an arbitrary identity (an
    email address, say) instead of the request's IP. Meant to be used
    alongside rate_limit(), not instead of it: per-IP alone can't catch
    an attacker spreading requests across many IPs at one target account
    - this closes that gap for sensitive per-account actions like
    password reset. Case-insensitive since email addresses are."""
    key = f"{bucket_name}:{identity.strip().lower()}"
    _check_and_record(key, max_attempts, window_seconds)
