import datetime as dt

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.database import get_db
from app.session import SESSION_COOKIE, csrf_ok
from app import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _user_from_token(token: str | None, db: Session) -> models.User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None
    # A password change/reset bumps token_valid_after to "now" - anything
    # issued before that (even if not yet expired) is a token that
    # existed before the account was secured, and shouldn't keep working.
    if user.token_valid_after:
        issued_at = payload.get("iat")
        # fromtimestamp(..., tz=utc) then stripping tzinfo, not the
        # deprecated utcfromtimestamp() - same naive-but-UTC convention
        # as every DateTime column in this app (see models.utcnow()).
        issued_dt = dt.datetime.fromtimestamp(issued_at, tz=dt.timezone.utc).replace(tzinfo=None) if issued_at else None
        if not issued_dt or issued_dt < user.token_valid_after:
            return None
    return user


def _resolve_token(request: Request, header_token: str | None) -> str | None:
    """Prefer the HttpOnly session cookie, fall back to the header.

    The app's own frontend uses the cookie and no longer keeps a copy of
    the token anywhere script can reach. The Authorization header is still
    honoured so scripts and other API clients keep working.
    """
    return request.cookies.get(SESSION_COOKIE) or header_token


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = _user_from_token(_resolve_token(request, token), db)
    if user is None:
        raise credentials_exception
    if not csrf_ok(request):
        # Cookie-authenticated write without a matching CSRF token.
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")
    return user


def get_optional_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User | None:
    if not csrf_ok(request):
        return None
    return _user_from_token(_resolve_token(request, token), db)


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
