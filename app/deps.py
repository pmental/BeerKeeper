import datetime as dt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.database import get_db
from app import config, models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _local_user(db: Session) -> models.User:
    """Single-user desktop mode: there is exactly one user (id=1, created
    at startup by admin_bootstrap.ensure_local_user_exists), and every
    request acts as that user - there's no login, so no token to check."""
    user = db.query(models.User).filter(models.User.id == 1).first()
    if not user:
        # Shouldn't happen - ensure_local_user_exists runs before the app
        # accepts any requests - but fail loudly rather than as a 401
        # that looks like a login problem if it somehow does.
        raise HTTPException(status_code=500, detail="Local user not initialized.")
    return user


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


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if config.SINGLE_USER_MODE:
        return _local_user(db)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = _user_from_token(token, db)
    if user is None:
        raise credentials_exception
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User | None:
    if config.SINGLE_USER_MODE:
        return _local_user(db)
    return _user_from_token(token, db)


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    # In single-user mode the local user is always the admin (there's
    # nobody else it could mean) - see ensure_local_user_exists.
    if not config.SINGLE_USER_MODE and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
