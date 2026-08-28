from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.routers.beers import resolve_or_create_beer_id

router = APIRouter(prefix="/api/wanted", tags=["wanted"])


@router.get("", response_model=list[schemas.WantedEntryOut])
def list_wanted(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entries = (
        db.query(models.WantedEntry)
        .options(joinedload(models.WantedEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.WantedEntry.user_id == current_user.id)
        .all()
    )
    entries.sort(key=lambda e: (e.beer.name.lower(), e.beer.brewery.name.lower()))
    return entries


@router.post("", response_model=schemas.WantedEntryOut)
def add_wanted(
    payload: schemas.WantedEntryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    beer_id = resolve_or_create_beer_id(db, payload.beer_id, payload.beer)

    entry = models.WantedEntry(user_id=current_user.id, beer_id=beer_id, notes=payload.notes)
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That beer is already on your wanted list.")
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_wanted(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = (
        db.query(models.WantedEntry)
        .filter(models.WantedEntry.id == entry_id, models.WantedEntry.user_id == current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Wanted entry not found.")
    db.delete(entry)
    db.commit()
    return {"ok": True}
