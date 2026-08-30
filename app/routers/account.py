from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import verify_password
from app.database import get_db
from app.deps import get_current_user
from app.email import is_smtp_enabled, send_email_safely

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("", response_model=schemas.AccountOut)
def get_account(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("", response_model=schemas.AccountOut)
def update_account(
    payload: schemas.AccountPatch,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    current_password = data.pop("current_password", None)

    old_email = current_user.email
    changing_email = "email" in data and data["email"] != old_email
    if changing_email:
        # A stolen-but-not-yet-expired token shouldn't be enough by itself
        # to redirect this account's password-reset emails somewhere an
        # attacker controls - require proof you know the password too,
        # the same bar as actually changing the password.
        if not current_password or not verify_password(current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Enter your current password to change your email.")

    for field, value in data.items():
        setattr(current_user, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That email is already in use.")
    db.refresh(current_user)

    if changing_email and is_smtp_enabled(db):
        background_tasks.add_task(
            send_email_safely,
            old_email,
            "Your account email was changed",
            (
                f"Hi {current_user.username},\n\n"
                f"Your account's email address was just changed from this address to "
                f"{current_user.email}.\n\n"
                f"If that wasn't you, someone may have access to your account - change "
                f"your password immediately and contact your admin.\n"
            ),
        )

    return current_user
