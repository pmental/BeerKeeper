import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/consumption", tags=["consumption"])


@router.get("", response_model=list[schemas.ConsumptionLogOut])
def list_consumption(
    beer_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = (
        db.query(models.ConsumptionLog)
        .options(joinedload(models.ConsumptionLog.beer).joinedload(models.Beer.brewery))
        .filter(models.ConsumptionLog.user_id == current_user.id)
    )
    if beer_id:
        query = query.filter(models.ConsumptionLog.beer_id == beer_id)
    return query.order_by(models.ConsumptionLog.consumed_on.desc()).all()


@router.post("", response_model=schemas.ConsumptionLogOut)
def add_consumption(
    payload: schemas.ConsumptionLogIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Log a tasting note for a beer you didn't have tracked in your cellar
    (e.g. one you drank at a bar)."""
    beer = db.query(models.Beer).filter(models.Beer.id == payload.beer_id).first()
    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found.")
    log = models.ConsumptionLog(
        user_id=current_user.id,
        beer_id=payload.beer_id,
        quantity=payload.quantity,
        consumed_on=payload.consumed_on or dt.date.today(),
        note=payload.note,
        rating=payload.rating,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.delete("/{log_id}")
def delete_consumption(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    log = (
        db.query(models.ConsumptionLog)
        .filter(models.ConsumptionLog.id == log_id, models.ConsumptionLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found.")
    db.delete(log)
    db.commit()
    return {"ok": True}
