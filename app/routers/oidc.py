import re
import secrets

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import config, models
from app.admin_bootstrap import promote_earliest_if_no_admin
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
    # Used when the OIDC provider doesn't release an email claim - just
    # needs to be syntactically valid and non-colliding, since the account
    # is genuinely never emailed. RFC 2606's ".invalid" would be the more
    # "correct" choice semantically, but Pydantic's EmailStr rejects known
    # special-use TLDs like .invalid/.test/.local outright, which broke
    # every response returning this account (e.g. every /api/auth/me call)
    # with a 500. This domain isn't on that reserved list.
    return f"{username}@no-reply.beerkeeper.internal"


def _find_or_create_user(
    db: Session, sub: str, email: str | None, preferred_username: str | None, display_name: str | None
) -> models.User:
    user = db.query(models.User).filter(models.User.oidc_subject == sub).first()
    if user:
        # Keep the display name in sync with the provider on every login
        # (e.g. after a legal name change), but don't clear it just
        # because a particular login response happened to omit the claim.
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            db.commit()
            db.refresh(user)
        return user

    # First-time login for this OIDC identity. Link to a matching local
    # account by email if one exists and isn't already linked elsewhere;
    # otherwise provision a brand new account.
    if email:
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing and not existing.oidc_subject:
            existing.oidc_subject = sub
            if display_name:
                existing.display_name = display_name
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
        display_name=display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    promote_earliest_if_no_admin(db)
    db.refresh(user)  # pick up is_admin if this was the promotion
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

    # Some providers put a full claim set in the ID token; others put only
    # the bare minimum there (sometimes just `sub`) and expect the rest
    # (name, email, ...) to come from a separate call to the userinfo
    # endpoint - so both are worth checking. But the two responses aren't
    # always the same shape: a provider's userinfo endpoint can return a
    # SPARSER set than its ID token (e.g. a custom claim only embedded in
    # the token itself), so a naive merge that lets the endpoint's keys
    # unconditionally win can silently overwrite a good value with a
    # missing/null one. Prefer whichever source actually has a non-empty
    # value for each field, with the (signed, more trustworthy) ID token
    # winning if both happen to have one.
    id_token_info = dict(token.get("userinfo") or {})
    try:
        endpoint_info = await oauth.oidc.userinfo(token=token) or {}
    except Exception:
        endpoint_info = {}  # no userinfo endpoint, or it failed - work with whatever the ID token had

    userinfo = dict(endpoint_info)
    for key, value in id_token_info.items():
        if value not in (None, ""):
            userinfo[key] = value

    sub = userinfo.get("sub")
    if not sub:
        return RedirectResponse(f"{config.BASE_URL}/#/login?oidc_error=missing_subject")

    email = userinfo.get("email")
    preferred_username = userinfo.get("preferred_username") or userinfo.get("nickname")
    # "name" is the standard OIDC claim for a full display name, but not
    # every provider sends it even when it sends the pieces - fall back to
    # combining given_name/family_name if that's all that's available.
    display_name = userinfo.get("name")
    if not display_name:
        parts = [userinfo.get("given_name"), userinfo.get("family_name")]
        joined = " ".join(p for p in parts if p)
        display_name = joined or None

    db = SessionLocal()
    try:
        user = _find_or_create_user(db, sub, email, preferred_username, display_name)
        jwt_token = create_access_token(user.id, user.username)
    finally:
        db.close()

    # Diagnostic line for exactly the situation that prompted adding it:
    # "my provider has a name claim but the app isn't showing it." Doesn't
    # print claim VALUES (some may be sensitive) beyond display_name itself,
    # just which claim keys came back and what got resolved, so a
    # `docker compose logs` after a login attempt is actually useful for
    # tracking down provider-specific claim-shape issues without needing
    # access to the real token.
    print(
        f"[oidc] login: claims_received={sorted(userinfo.keys())} "
        f"resolved_display_name={display_name!r} resolved_username={user.username!r}"
    )

    return RedirectResponse(f"{config.BASE_URL}/#/oidc-callback?token={jwt_token}")
