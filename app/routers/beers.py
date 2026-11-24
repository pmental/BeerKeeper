from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import eq_unicode, get_db, search_unicode
from app.deps import get_current_user
from app.url_utils import sanitize_url

router = APIRouter(prefix="/api/beers", tags=["beers"])
brewery_router = APIRouter(prefix="/api/breweries", tags=["breweries"])


def _user_beer_recency(db: Session, user_id: int) -> dict[int, object]:
    """Most-recent-use timestamp per beer_id for this user, drawn from both
    their cellar entries and their drinking history, so a beer they've had
    before (even if no longer in their cellar) still surfaces first."""
    recency: dict[int, object] = {}

    for beer_id, ts in db.query(models.CellarEntry.beer_id, models.CellarEntry.updated_at).filter(
        models.CellarEntry.user_id == user_id
    ):
        if beer_id not in recency or ts > recency[beer_id]:
            recency[beer_id] = ts

    for beer_id, ts in db.query(models.ConsumptionLog.beer_id, models.ConsumptionLog.created_at).filter(
        models.ConsumptionLog.user_id == user_id
    ):
        if beer_id not in recency or ts > recency[beer_id]:
            recency[beer_id] = ts

    return recency


def _user_brewery_recency(db: Session, user_id: int) -> dict[int, object]:
    """Same idea as above, rolled up to the brewery level via each beer's
    brewery_id, so a brewery you've used before ranks first even for a
    beer of theirs you haven't personally logged yet."""
    beer_recency = _user_beer_recency(db, user_id)
    if not beer_recency:
        return {}
    brewery_by_beer = dict(
        db.query(models.Beer.id, models.Beer.brewery_id).filter(models.Beer.id.in_(beer_recency.keys()))
    )
    recency: dict[int, object] = {}
    for beer_id, ts in beer_recency.items():
        brewery_id = brewery_by_beer.get(beer_id)
        if brewery_id is None:
            continue
        if brewery_id not in recency or ts > recency[brewery_id]:
            recency[brewery_id] = ts
    return recency


def _search_with_recency(query, model, recency: dict):
    """Shared by search_breweries and search_beers below.

    The alphabetical candidate set is capped, since sorting a catalog of
    thousands in Python on every keystroke doesn't scale. A cap alone
    would hide anything the user has used that sorts past it (with 10,000
    names, the first 500 only reach about "D"), so their own recently used
    rows are fetched separately and always included; the cap only trims
    everything else."""
    results = query.order_by(model.name).limit(500).all()
    if recency:
        seen_ids = {r.id for r in results}
        missing_ids = [rid for rid in recency if rid not in seen_ids]
        if missing_ids:
            results.extend(query.filter(model.id.in_(missing_ids)).all())

        def sort_key(r):
            used = r.id in recency
            # Used-before items first (0 before 1), most-recently-used
            # first within that group; everything else falls back to
            # alphabetical.
            return (0 if used else 1, -recency[r.id].timestamp() if used else 0, r.name.lower())

        results.sort(key=sort_key)

    return results[:25]


@brewery_router.get("", response_model=list[schemas.BreweryOut])
def search_breweries(
    q: str = "",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Brewery)
    if q:
        query = query.filter(search_unicode(models.Brewery.name, f"%{q}%"))

    recency = _user_brewery_recency(db, current_user.id)
    return _search_with_recency(query, models.Brewery, recency)


@brewery_router.post("", response_model=schemas.BreweryOut)
def create_brewery(
    payload: schemas.BreweryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    name = payload.name.strip()
    existing = db.query(models.Brewery).filter(eq_unicode(models.Brewery.name, name)).first()
    if existing:
        return existing
    brewery = models.Brewery(name=name, website=sanitize_url(payload.website))
    db.add(brewery)
    db.commit()
    db.refresh(brewery)
    return brewery


def _get_or_create_brewery(db: Session, brewery_id: int | None, new_name: str | None) -> models.Brewery:
    if brewery_id:
        brewery = db.query(models.Brewery).filter(models.Brewery.id == brewery_id).first()
        if not brewery:
            raise HTTPException(status_code=404, detail="Brewery not found.")
        return brewery
    if new_name:
        name = new_name.strip()
        existing = db.query(models.Brewery).filter(eq_unicode(models.Brewery.name, name)).first()
        if existing:
            return existing
        brewery = models.Brewery(name=name)
        db.add(brewery)
        db.flush()
        return brewery
    raise HTTPException(status_code=400, detail="A brewery_id or new_brewery_name is required.")


def resolve_or_create_beer_id(db: Session, beer_id: int | None, beer_in: "schemas.BeerIn | None") -> int:
    """Shared by any endpoint that accepts either an existing beer_id or
    inline beer details (CellarEntryIn.beer, WantedEntryIn.beer, ...):
    reuses a matching existing beer/brewery by name when possible, else
    creates them. Returns the resolved beer_id."""
    if beer_id:
        if not db.query(models.Beer).filter(models.Beer.id == beer_id).first():
            raise HTTPException(status_code=404, detail="Beer not found.")
        return beer_id

    if not beer_in:
        raise HTTPException(status_code=400, detail="Provide a beer_id or beer details.")

    brewery = _get_or_create_brewery(db, beer_in.brewery_id, beer_in.new_brewery_name)
    beer = (
        db.query(models.Beer)
        .filter(models.Beer.brewery_id == brewery.id, eq_unicode(models.Beer.name, beer_in.name.strip()))
        .first()
    )
    if not beer:
        beer = models.Beer(
            name=beer_in.name.strip(),
            brewery_id=brewery.id,
            style=beer_in.style,
            abv=beer_in.abv,
            description=beer_in.description,
            reference_url=sanitize_url(beer_in.reference_url),
        )
        db.add(beer)
        db.flush()
    return beer.id


@router.get("", response_model=list[schemas.BeerOut])
def search_beers(
    q: str = "",
    brewery_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Beer)
    if brewery_id:
        query = query.filter(models.Beer.brewery_id == brewery_id)
    if q:
        query = query.join(models.Brewery).filter(
            or_(search_unicode(models.Beer.name, f"%{q}%"), search_unicode(models.Brewery.name, f"%{q}%"))
        )

    recency = _user_beer_recency(db, current_user.id)
    return _search_with_recency(query, models.Beer, recency)


@router.get("/{beer_id}", response_model=schemas.BeerOut)
def get_beer(beer_id: int, db: Session = Depends(get_db), _user: models.User = Depends(get_current_user)):
    beer = db.query(models.Beer).filter(models.Beer.id == beer_id).first()
    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found.")
    return beer


@router.post("", response_model=schemas.BeerOut)
def create_beer(
    payload: schemas.BeerIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    brewery = _get_or_create_brewery(db, payload.brewery_id, payload.new_brewery_name)
    existing = (
        db.query(models.Beer)
        .filter(models.Beer.brewery_id == brewery.id, eq_unicode(models.Beer.name, payload.name.strip()))
        .first()
    )
    if existing:
        return existing
    beer = models.Beer(
        name=payload.name.strip(),
        brewery_id=brewery.id,
        style=payload.style,
        abv=payload.abv,
        description=payload.description,
        reference_url=sanitize_url(payload.reference_url),
    )
    db.add(beer)
    db.commit()
    db.refresh(beer)
    return beer
