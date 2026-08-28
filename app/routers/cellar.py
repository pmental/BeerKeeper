import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.routers.beers import _get_or_create_brewery

router = APIRouter(prefix="/api/cellar", tags=["cellar"])


def _entry_query(db: Session, user_id: int):
    return (
        db.query(models.CellarEntry)
        .options(joinedload(models.CellarEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.CellarEntry.user_id == user_id)
    )


@router.get("", response_model=list[schemas.CellarEntryOut])
def list_cellar(
    sort: str | None = None,
    location: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = _entry_query(db, current_user.id)
    if location:
        query = query.filter(models.CellarEntry.location == location)
    entries = query.all()

    sort_key = sort or current_user.default_sort
    if sort_key == "brewery":
        entries.sort(key=lambda e: (e.beer.brewery.name.lower(), e.beer.name.lower()))
    else:
        entries.sort(key=lambda e: (e.beer.name.lower(), e.beer.brewery.name.lower()))
    return entries


@router.post("", response_model=schemas.CellarEntryOut)
def add_entry(
    payload: schemas.CellarEntryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    beer_id = payload.beer_id
    if not beer_id and payload.beer:
        brewery = _get_or_create_brewery(db, payload.beer.brewery_id, payload.beer.new_brewery_name)
        beer = (
            db.query(models.Beer)
            .filter(models.Beer.brewery_id == brewery.id, models.Beer.name.ilike(payload.beer.name))
            .first()
        )
        if not beer:
            beer = models.Beer(
                name=payload.beer.name.strip(),
                brewery_id=brewery.id,
                style=payload.beer.style,
                abv=payload.beer.abv,
                description=payload.beer.description,
                reference_url=payload.beer.reference_url,
            )
            db.add(beer)
            db.flush()
        beer_id = beer.id

    if not beer_id:
        raise HTTPException(status_code=400, detail="Provide a beer_id or beer details.")
    if not db.query(models.Beer).filter(models.Beer.id == beer_id).first():
        raise HTTPException(status_code=404, detail="Beer not found.")

    entry = models.CellarEntry(
        user_id=current_user.id,
        beer_id=beer_id,
        location=payload.location,
        custom_location=payload.custom_location,
        quantity=payload.quantity,
        size_oz=payload.size_oz,
        bottle_date=payload.bottle_date,
        best_before=payload.best_before,
        batch_notes=payload.batch_notes,
        trade_status=payload.trade_status if current_user.trading_enabled else "none",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _get_owned_entry(db: Session, entry_id: int, user_id: int) -> models.CellarEntry:
    entry = (
        _entry_query(db, user_id).filter(models.CellarEntry.id == entry_id).first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Cellar entry not found.")
    return entry


@router.patch("/{entry_id}", response_model=schemas.CellarEntryOut)
def update_entry(
    entry_id: int,
    payload: schemas.CellarEntryPatch,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.post("/{entry_id}/move", response_model=schemas.CellarEntryOut)
def move_entry(
    entry_id: int,
    payload: schemas.MoveIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    entry.location = payload.location
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/drink", response_model=schemas.CellarEntryOut)
def drink_entry(
    entry_id: int,
    payload: schemas.DrinkIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Decrement an entry's quantity and record an independent consumption log
    (tasting note + rating) that survives even if the entry is later deleted."""
    entry = _get_owned_entry(db, entry_id, current_user.id)
    if payload.quantity > entry.quantity:
        raise HTTPException(status_code=400, detail="Can't drink more than you have.")

    log = models.ConsumptionLog(
        user_id=current_user.id,
        beer_id=entry.beer_id,
        quantity=payload.quantity,
        consumed_on=payload.consumed_on or dt.date.today(),
        note=payload.note,
        rating=payload.rating,
    )
    db.add(log)
    entry.quantity -= payload.quantity

    if entry.quantity == 0 and payload.delete_if_empty:
        # Snapshot the response before the row disappears out from under us.
        snapshot = schemas.CellarEntryOut.model_validate(entry)
        snapshot.quantity = 0
        db.delete(entry)
        db.commit()
        return snapshot

    db.commit()
    db.refresh(entry)
    return entry
