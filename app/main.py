import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import auth, config
from app.database import Base, engine, run_migrations, SessionLocal
from app import models  # noqa: F401  (ensures models are registered before create_all)
from app.brewery_seed import seed_breweries_if_needed
from app.routers import auth as auth_router
from app.routers import beers, cellar, consumption, account, public, import_export, oidc, beer_styles, wanted

Base.metadata.create_all(bind=engine)
run_migrations()

_seed_db = SessionLocal()
try:
    seed_breweries_if_needed(_seed_db)
finally:
    _seed_db.close()

app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION)

# Only used to hold the short-lived state/nonce for the OIDC handshake (a
# few seconds, during the redirect to and back from the identity provider).
# It is unrelated to the app's own login sessions, which are JWT bearer
# tokens sent in the Authorization header, not cookies.
app.add_middleware(SessionMiddleware, secret_key=auth.SECRET_KEY, same_site="lax")

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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    return {"name": config.APP_NAME, "version": config.APP_VERSION}

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


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
