import datetime as dt
import hashlib
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.admin_bootstrap import promote_earliest_if_no_admin
from app.auth import create_access_token, hash_password, verify_password
from app.database import get_db
from app.deps import get_current_user
from app.email import is_smtp_enabled, send_password_reset_email, send_welcome_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

RESET_TOKEN_LIFETIME = dt.timedelta(hours=1)


def _require_password_auth():
    if not config.PASSWORD_AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="Password-based authentication is disabled on this instance.")


def _get_instance_settings(db: Session) -> models.InstanceSettings:
    settings = db.query(models.InstanceSettings).filter(models.InstanceSettings.id == 1).first()
    if not settings:
        # Should always exist by the time a request comes in (seeded at
        # startup), but don't let a request 500 if it's somehow missing.
        settings = models.InstanceSettings(id=1, registration_enabled=True)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _create_reset_token(db: Session, user: models.User) -> str:
    # A fresh request supersedes any previous outstanding one, so only the
    # most recently requested link is ever valid.
    db.query(models.PasswordResetToken).filter(models.PasswordResetToken.user_id == user.id).delete()
    raw_token = secrets.token_urlsafe(32)
    db.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=dt.datetime.utcnow() + RESET_TOKEN_LIFETIME,
        )
    )
    db.commit()
    return raw_token


@router.get("/config", response_model=schemas.AuthConfigOut)
def auth_config(db: Session = Depends(get_db)):
    return schemas.AuthConfigOut(
        password_auth_enabled=config.PASSWORD_AUTH_ENABLED,
        oidc_enabled=config.OIDC_ENABLED,
        oidc_button_label=config.OIDC_BUTTON_LABEL,
        registration_enabled=_get_instance_settings(db).registration_enabled,
        smtp_enabled=is_smtp_enabled(db),
    )


@router.post("/register", response_model=schemas.TokenOut)
def register(payload: schemas.RegisterIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    _require_password_auth()
    if not _get_instance_settings(db).registration_enabled:
        raise HTTPException(status_code=403, detail="New registrations are disabled on this instance.")
    user = models.User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That username or email is already taken.")
    db.refresh(user)
    promote_earliest_if_no_admin(db)
    db.refresh(user)  # pick up is_admin if this was the promotion
    if is_smtp_enabled(db):
        background_tasks.add_task(send_welcome_email, user.email, user.username)
    token = create_access_token(user.id, user.username)
    return schemas.TokenOut(access_token=token)


@router.post("/login", response_model=schemas.TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    _require_password_auth()
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    token = create_access_token(user.id, user.username)
    return schemas.TokenOut(access_token=token)


@router.get("/me", response_model=schemas.AccountOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(
    payload: schemas.ChangePasswordIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_password_auth()
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(payload: schemas.ForgotPasswordIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    _require_password_auth()
    if not is_smtp_enabled(db):
        raise HTTPException(
            status_code=403, detail="Email isn't configured on this instance - ask an admin to reset your password."
        )
    # Always the same response whether or not the email matches an account,
    # so this can't be used to check which emails have accounts here.
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if user:
        raw_token = _create_reset_token(db, user)
        background_tasks.add_task(send_password_reset_email, user.email, user.username, raw_token)
    return {"ok": True, "detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password", response_model=schemas.TokenOut)
def reset_password(payload: schemas.ResetPasswordIn, db: Session = Depends(get_db)):
    _require_password_auth()
    token_hash = _hash_token(payload.token)
    reset = db.query(models.PasswordResetToken).filter(models.PasswordResetToken.token_hash == token_hash).first()
    if not reset or reset.used or reset.expires_at < dt.datetime.utcnow():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")

    user = db.query(models.User).filter(models.User.id == reset.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")

    user.password_hash = hash_password(payload.new_password)
    reset.used = True
    db.commit()
    token = create_access_token(user.id, user.username)
    return schemas.TokenOut(access_token=token)
