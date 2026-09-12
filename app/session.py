"""Cookie-based session handling.

The access token used to live in localStorage, which meant any script
running on the page could read it. It's now delivered as an HttpOnly
cookie instead, so script can't touch it at all - the point being that
this app is self-hosted by people whose deployments can't be audited from
here. Someone may run it behind a CDN that injects its own JavaScript, or
a proxy that drops the Content-Security-Policy header, and the token
shouldn't be reachable when that happens.

The token is still returned in the login response body, because scripts
and other API clients legitimately use it as a Bearer token. What changed
is that the app's own frontend no longer stores it anywhere.

Moving to cookies means the browser attaches credentials automatically,
which is what makes CSRF possible, so that has to be answered too. Two
things do it here: SameSite=Lax, which stops the browser sending the
cookie on cross-site POSTs at all, and a double-submit token for
defence in depth against a same-site attacker (a neighbouring subdomain,
say). The CSRF cookie is deliberately readable by script - it isn't a
secret, it just has to be something a cross-origin page can't read in
order to echo it back in a header.
"""

import secrets

from fastapi import Request, Response

from app.auth import TOKEN_EXPIRE_DAYS

SESSION_COOKIE = "cellar_session"
CSRF_COOKIE = "cellar_csrf"
CSRF_HEADER = "X-CSRF-Token"

_MAX_AGE = TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _is_secure(request: Request) -> bool:
    """Whether to mark cookies Secure.

    Deliberately derived from the request rather than hardcoded: a Secure
    cookie is simply not sent over plain http, so setting it
    unconditionally would lock out anyone running this on a LAN address
    without TLS - which is a perfectly normal way to self-host. Checks the
    forwarded header too, since the common case is TLS terminating at a
    reverse proxy or tunnel and the app itself only ever seeing http.
    """
    if request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
        return True
    return request.url.scheme == "https"


def start_session(response: Response, request: Request, token: str) -> None:
    """Attach the session and CSRF cookies to a response."""
    secure = _is_secure(request)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=_MAX_AGE,
        httponly=False,  # the frontend has to read this to echo it back
        secure=secure,
        samesite="lax",
        path="/",
    )


def end_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def csrf_ok(request: Request) -> bool:
    """Double-submit check, for requests authenticated by cookie.

    Only relevant when the browser supplied the credential on its own. A
    request carrying an explicit Authorization header was assembled by
    something that already had the token, which a cross-site page can't
    do, so there's nothing to forge.
    """
    if request.headers.get("authorization"):
        return True
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    sent = request.headers.get(CSRF_HEADER)
    stored = request.cookies.get(CSRF_COOKIE)
    return bool(sent and stored and secrets.compare_digest(sent, stored))
