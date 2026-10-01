import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.routers.beers import resolve_or_create_beer_id
from app.units import OZ_TO_ML

router = APIRouter(prefix="/api/cellar", tags=["cellar"])


def _entry_query(db: Session, user_id: int):
    return (
        db.query(models.CellarEntry)
        .options(joinedload(models.CellarEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.CellarEntry.user_id == user_id)
    )


def sort_entries(entries: list, sort_key: str, direction: str = "asc") -> list:
    """Shared by list_cellar and the public cellar view so 'beer' / 'brewery'
    / 'drinkby' mean the same thing everywhere. Entries with no best_before
    date sort after ones that have it, rather than being scattered in
    among a default (e.g. today's) date - true in both directions, since
    flipping the date order shouldn't also flip whether undated entries
    show up first or last."""
    reverse = direction == "desc"
    if sort_key == "brewery":
        entries.sort(key=lambda e: (e.beer.brewery.name.lower(), e.beer.name.lower()), reverse=reverse)
    elif sort_key == "drinkby":
        dated = [e for e in entries if e.best_before is not None]
        undated = [e for e in entries if e.best_before is None]
        dated.sort(key=lambda e: (e.best_before, e.beer.name.lower()), reverse=reverse)
        undated.sort(key=lambda e: e.beer.name.lower())
        entries = dated + undated
    else:
        entries.sort(key=lambda e: (e.beer.name.lower(), e.beer.brewery.name.lower()), reverse=reverse)
    return entries


@router.get("", response_model=list[schemas.CellarEntryOut])
def list_cellar(
    sort: str | None = None,
    direction: str = "asc",
    location: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = _entry_query(db, current_user.id)
    if location:
        query = query.filter(models.CellarEntry.location == location)
    entries = query.all()

    sort_key = sort or current_user.default_sort
    return sort_entries(entries, sort_key, direction if direction in ("asc", "desc") else "asc")


@router.get("/sizes", response_model=list[float])
def list_used_sizes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Distinct bottle/can sizes (in oz, the canonical storage unit) this
    user has entered before, most-used first - so a size they've typed
    once shows up as a suggestion without retyping, on top of the fixed
    common-sizes list the frontend already offers."""
    rows = (
        db.query(models.CellarEntry.size_oz, func.count(models.CellarEntry.id).label("uses"))
        .filter(models.CellarEntry.user_id == current_user.id, models.CellarEntry.size_oz.isnot(None))
        .group_by(models.CellarEntry.size_oz)
        .order_by(func.count(models.CellarEntry.id).desc())
        .all()
    )
    return [r[0] for r in rows]


@router.post("", response_model=schemas.CellarEntryOut)
def add_entry(
    payload: schemas.CellarEntryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    beer_id = resolve_or_create_beer_id(db, payload.beer_id, payload.beer)

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

    # A reminder already sent covers the bottle as it was then. If the
    # drink-by date moves, or an entry comes back from zero to having
    # bottles in it, that's a new situation worth being told about - so
    # the marker is cleared and the next sweep treats it as unreminded.
    # Without this, pushing a date out by a year would silently suppress
    # the reminder for the new date.
    date_changed = "best_before" in data and data["best_before"] != entry.best_before
    refilled = "quantity" in data and entry.quantity == 0 and (data["quantity"] or 0) > 0
    if date_changed or refilled:
        entry.drinkby_notified_at = None

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


def _text_matches(column, value):
    """Notes and locations compare after trimming, with blank and missing
    treated as the same - "Nice one " typed by hand and "Nice one" from a
    CSV are the same note."""
    value = (value or "").strip()
    if not value:
        return or_(column.is_(None), func.trim(column) == "")
    return func.trim(column) == value


def _size_matches(column, size_oz):
    """Sizes compare by whole millilitres rather than exact floats. The UI
    stores ounces rounded to three places and a CSV may arrive in either
    unit, so the same 750 ml bottle can be stored as slightly different
    numbers; no two real bottle sizes are within a millilitre of each
    other."""
    if size_oz is None:
        return column.is_(None)
    return func.round(column * OZ_TO_ML) == round(size_oz * OZ_TO_ML)


def find_matching_entry(
    db: Session,
    *,
    user_id: int,
    beer_id: int,
    location: str,
    custom_location,
    size_oz,
    bottle_date,
    best_before,
    batch_notes,
    trade_status: str,
    exclude_id=None,
):
    """An existing entry that bottles with these details belong to.

    Matches on everything that distinguishes one batch from another, not
    just the beer: bottles that differ in size, bottling or drink-by date,
    notes or location are kept apart. Used wherever bottles are added to
    a cellar, so moving or importing a bottle that's already there adds to
    the existing row instead of creating a duplicate.
    """
    query = db.query(models.CellarEntry).filter(
        models.CellarEntry.user_id == user_id,
        models.CellarEntry.beer_id == beer_id,
        models.CellarEntry.location == location,
        _text_matches(models.CellarEntry.custom_location, custom_location),
        _size_matches(models.CellarEntry.size_oz, size_oz),
        models.CellarEntry.bottle_date == bottle_date,
        models.CellarEntry.best_before == best_before,
        _text_matches(models.CellarEntry.batch_notes, batch_notes),
        models.CellarEntry.trade_status == trade_status,
    )
    if exclude_id is not None:
        query = query.filter(models.CellarEntry.id != exclude_id)
    return query.first()


@router.post("/{entry_id}/move", response_model=schemas.CellarEntryOut)
def move_entry(
    entry_id: int,
    payload: schemas.MoveIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Move some of an entry's bottles to the other location.

    Defaults to a single bottle, leaving any others where they are - the
    button in the UI is per-entry, not per-bottle, and moving a whole
    six-pack because you took one out for the fridge isn't what anyone
    means by it. Returns the entry the bottles landed in.
    """
    entry = _get_owned_entry(db, entry_id, current_user.id)

    if payload.location == entry.location:
        return entry

    qty = payload.quantity
    if qty > entry.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {entry.quantity} bottle{'' if entry.quantity == 1 else 's'} to move.",
        )

    target = find_matching_entry(
        db,
        user_id=entry.user_id,
        beer_id=entry.beer_id,
        location=payload.location,
        custom_location=entry.custom_location,
        size_oz=entry.size_oz,
        bottle_date=entry.bottle_date,
        best_before=entry.best_before,
        batch_notes=entry.batch_notes,
        trade_status=entry.trade_status,
        exclude_id=entry.id,
    )

    if qty == entry.quantity:
        # Moving the lot. Fold into a matching entry if one's already
        # there, otherwise just relabel this one rather than churning rows.
        if target:
            target.quantity += qty
            db.delete(entry)
        else:
            entry.location = payload.location
            target = entry
    else:
        entry.quantity -= qty
        if target:
            target.quantity += qty
        else:
            target = models.CellarEntry(
                user_id=entry.user_id,
                beer_id=entry.beer_id,
                location=payload.location,
                custom_location=entry.custom_location,
                quantity=qty,
                size_oz=entry.size_oz,
                bottle_date=entry.bottle_date,
                best_before=entry.best_before,
                batch_notes=entry.batch_notes,
                trade_status=entry.trade_status,
            )
            db.add(target)

    db.commit()
    db.refresh(target)
    return target


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
        best_before=entry.best_before,
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
