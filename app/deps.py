import datetime as dt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.database import get_db
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
        if not issued_at or dt.datetime.utcfromtimestamp(issued_at) < user.token_valid_after:
            return None
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
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
    return _user_from_token(token, db)


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user
