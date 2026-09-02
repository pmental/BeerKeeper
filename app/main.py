import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import auth, config
from app.deps import get_current_user
from app.database import Base, engine, run_migrations, SessionLocal
from app import models  # noqa: F401  (ensures models are registered before create_all)
from app.backup import apply_pending_restore_if_any
from app.brewery_seed import seed_breweries_if_needed
from app.beer_styles import migrate_beer_styles_if_needed
from app.admin_bootstrap import ensure_instance_settings, ensure_admin_exists
from app.routers import auth as auth_router
from app.routers import beers, cellar, consumption, account, public, import_export, oidc, beer_styles, wanted, admin

# Must run before create_all/engine touches the database file at all - a
# staged restore (see app/backup.py) replaces that file outright, and
# swapping it out from under an already-open connection is exactly the
# kind of thing that corrupts data. This is why the swap only ever
# happens here, at a clean startup, never from a live request.
apply_pending_restore_if_any()

Base.metadata.create_all(bind=engine)
run_migrations()

_seed_db = SessionLocal()
try:
    seed_breweries_if_needed(_seed_db)
    migrate_beer_styles_if_needed(_seed_db)
    ensure_instance_settings(_seed_db)
    ensure_admin_exists(_seed_db)
finally:
    _seed_db.close()

app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION)

# Only used to hold the short-lived state/nonce for the OIDC handshake (a
# few seconds, during the redirect to and back from the identity provider).
# It is unrelated to the app's own login sessions, which are JWT bearer
# tokens sent in the Authorization header, not cookies.
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.SECRET_KEY,
    same_site="lax",
    https_only=config.BASE_URL.startswith("https://"),
)

# Compresses response bodies (the JS/CSS bundle, JSON API responses) when
# the client supports it - pure transfer-size/speed win, no behavior
# change and nothing security-relevant here: it only touches the
# response body, not headers, auth, or anything else.
app.add_middleware(GZipMiddleware, minimum_size=500)


_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    # Every render site in this app builds HTML via inline style="..."
    # attributes rather than CSS classes - blocking that would break the
    # UI outright, so style-src allows it. script-src does not: that's
    # the directive that actually matters for XSS (it also covers inline
    # event-handler attributes like onclick=, not just <script> tags),
    # and the app has no inline scripts or handlers left to accommodate.
    "style-src 'self' 'unsafe-inline'; "
    # OIDC profile pictures are hosted by whatever the identity provider
    # is (Google, a self-hosted IdP, ...), not this app - 'self' alone
    # would block every one of them. Loosening only this directive is
    # deliberate and safe: an <img> tag can't execute script the way an
    # allowed script-src origin could, so this doesn't reopen the XSS
    # surface script-src is there to close.
    "img-src 'self' https:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["Referrer-Policy"] = "same-origin"
    # Every asset URL already carries a ?v=<app version> query string
    # (see the __APP_VERSION__ substitution below), so a new release
    # naturally serves a brand new URL - there's no risk of a browser
    # holding onto stale JS/CSS across an update. That's what makes it
    # safe to tell it to cache aggressively rather than revalidate on
    # every single page load.
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path.startswith("/api/"):
        # Explicit, not just "no header set" - a reverse proxy or CDN
        # sitting in front of this app (nginx, Cloudflare Tunnel, etc.)
        # has no way to know these responses are per-user and
        # authorization-dependent unless told outright. Without this,
        # a cache that doesn't vary by the Authorization header could
        # serve one person's response - success or failure - to someone
        # else entirely.
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth_router.router)
app.include_router(oidc.router)
app.include_router(beers.router)
app.include_router(beers.brewery_router)
app.include_router(cellar.router)
app.include_router(consumption.router)
app.include_router(account.router)
app.include_router(public.router)
app.include_router(import_export.router)
app.include_router(beer_styles.router)
app.include_router(wanted.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version(_user: models.User = Depends(get_current_user)):
    return {"name": config.APP_NAME, "version": config.APP_VERSION}

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/favicon.ico")
def favicon():
    # Browsers (and crawlers, RSS readers, etc.) probe /favicon.ico at the
    # domain root directly, independent of the <link rel="icon"> tags in
    # index.html - without this, the SPA catch-all below would swallow
    # that request and hand back the HTML page instead of an icon. Must be
    # registered before the catch-all route to take precedence.
    return FileResponse(os.path.join(STATIC_DIR, "icons", "favicon.ico"))


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    """Single-page app: hand every non-API path the same index.html and let the
    client-side router figure out what to show.

    Asset URLs in index.html carry a ?v=<version> query string (substituted
    here, so it's always automatically correct - never hand-maintained) so
    that bumping APP_VERSION forces browsers to fetch fresh JS/CSS instead
    of quietly continuing to serve a stale cached copy after an upgrade.
    The HTML document itself is served with no-cache so that substitution
    is always seen, even before the browser gets to the versioned assets.
    """
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found.")
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        html = f.read().replace("__APP_VERSION__", config.APP_VERSION)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})
