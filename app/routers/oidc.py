import re
import secrets

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import config, models
from app.auth import create_access_token, hash_password
from app.database import SessionLocal

router = APIRouter(prefix="/api/auth/oidc", tags=["oidc"])

oauth = OAuth()
if config.OIDC_ENABLED:
    oauth.register(
        name="oidc",
        server_metadata_url=f"{config.OIDC_ISSUER}/.well-known/openid-configuration",
        client_id=config.OIDC_CLIENT_ID,
        client_secret=config.OIDC_CLIENT_SECRET,
        client_kwargs={"scope": config.OIDC_SCOPES},
    )


def _require_oidc():
    if not config.OIDC_ENABLED:
        raise HTTPException(status_code=404, detail="OIDC is not enabled on this instance.")


def _sanitize_username(raw: str | None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", raw or "")
    if len(cleaned) < 3:
        cleaned = (cleaned + "user")[:3] if cleaned else "user"
    return cleaned[:32]


def _unique_username(db: Session, base: str) -> str:
    candidate = base
    n = 2
    while db.query(models.User).filter(models.User.username == candidate).first():
        suffix = str(n)
        candidate = base[: 32 - len(suffix)] + suffix
        n += 1
    return candidate


def _placeholder_email(username: str) -> str:
    # RFC 2606 reserves .invalid for exactly this: a syntactically valid
    # address that's guaranteed not to be a real, deliverable mailbox.
    return f"{username}@oidc.invalid"


def _find_or_create_user(db: Session, sub: str, email: str | None, preferred_username: str | None) -> models.User:
    user = db.query(models.User).filter(models.User.oidc_subject == sub).first()
    if user:
        return user

    # First-time login for this OIDC identity. Link to a matching local
    # account by email if one exists and isn't already linked elsewhere;
    # otherwise provision a brand new account.
    if email:
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing and not existing.oidc_subject:
            existing.oidc_subject = sub
            db.commit()
            db.refresh(existing)
            return existing

    base_username = _sanitize_username(preferred_username or (email.split("@")[0] if email else None))
    username = _unique_username(db, base_username)
    user = models.User(
        username=username,
        email=email or _placeholder_email(username),
        # OIDC-only accounts still need *some* password hash to satisfy the
        # NOT NULL column; this one is random and never handed to anyone,
        # so password login for this account will simply never succeed.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        oidc_subject=sub,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/login")
async def oidc_login(request: Request):
    _require_oidc()
    redirect_uri = f"{config.BASE_URL}/api/auth/oidc/callback"
    try:
        return await oauth.oidc.authorize_redirect(request, redirect_uri)
    except Exception as e:
        # Most commonly a bad CELLAR_OIDC_ISSUER (unreachable, wrong path, TLS
        # issue) that broke discovery. Send the browser back with a readable
        # message instead of a bare 500 and a stack trace.
        message = f"Couldn't reach the SSO provider ({type(e).__name__}: {e})."[:300]
        return RedirectResponse(f"{config.BASE_URL}/#/login?oidc_error=" + message)


@router.get("/callback")
async def oidc_callback(request: Request):
    _require_oidc()
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception as e:
        return RedirectResponse(f"{config.BASE_URL}/#/login?oidc_error=" + str(e)[:200])

    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.oidc.userinfo(token=token)
    sub = userinfo.get("sub")
    if not sub:
        return RedirectResponse(f"{config.BASE_URL}/#/login?oidc_error=missing_subject")

    email = userinfo.get("email")
    preferred_username = userinfo.get("preferred_username") or userinfo.get("nickname")

    db = SessionLocal()
    try:
        user = _find_or_create_user(db, sub, email, preferred_username)
        jwt_token = create_access_token(user.id, user.username)
    finally:
        db.close()

    return RedirectResponse(f"{config.BASE_URL}/#/oidc-callback?token={jwt_token}")
