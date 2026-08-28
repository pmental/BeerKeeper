from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("", response_model=schemas.AccountOut)
def get_account(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("", response_model=schemas.AccountOut)
def update_account(
    payload: schemas.AccountPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(current_user, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That email is already in use.")
    db.refresh(current_user)
    return current_user
