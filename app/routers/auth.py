from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, models, schemas
from app.auth import create_access_token, hash_password, verify_password
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _require_password_auth():
    if not config.PASSWORD_AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="Password-based authentication is disabled on this instance.")


@router.get("/config", response_model=schemas.AuthConfigOut)
def auth_config():
    return schemas.AuthConfigOut(
        password_auth_enabled=config.PASSWORD_AUTH_ENABLED,
        oidc_enabled=config.OIDC_ENABLED,
        oidc_button_label=config.OIDC_BUTTON_LABEL,
    )


@router.post("/register", response_model=schemas.TokenOut)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    _require_password_auth()
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
