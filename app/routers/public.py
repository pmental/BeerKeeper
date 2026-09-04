from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.deps import get_optional_user
from app.routers.cellar import sort_entries

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/cellars", response_model=list[schemas.PublicUserOut])
def browse_cellars(db: Session = Depends(get_db)):
    users = db.query(models.User).filter(models.User.cellar_public.is_(True)).all()
    # One aggregate query for every public user's count, instead of one
    # query per user - same fix as the admin Beers panel's usage counts.
    counts = dict(
        db.query(models.CellarEntry.user_id, func.coalesce(func.sum(models.CellarEntry.quantity), 0))
        .filter(models.CellarEntry.user_id.in_([u.id for u in users]))
        .group_by(models.CellarEntry.user_id)
        .all()
    )
    out = []
    for u in users:
        out.append(
            schemas.PublicUserOut(
                username=u.username,
                display_name=u.display_name,
                cellar_count=counts.get(u.id, 0),
                trading_enabled=u.trading_enabled,
            )
        )
    out.sort(key=lambda p: p.username.lower())
    return out


@router.get("/recent", response_model=list[schemas.RecentConsumedOut])
def recent_activity(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User | None = Depends(get_optional_user),
):
    # Everyone sees activity from users with a public cellar; if you're
    # logged in, your own activity is included too regardless of your own
    # privacy setting - this only ever adds YOUR rows for YOUR request, it
    # doesn't expose a private user's activity to anyone else.
    visibility = models.User.cellar_public.is_(True)
    if current_user:
        visibility = or_(visibility, models.User.id == current_user.id)

    logs = (
        db.query(models.ConsumptionLog)
        .join(models.User)
        .join(models.Beer)
        .join(models.Brewery)
        .filter(visibility)
        .options(
            joinedload(models.ConsumptionLog.user),
            joinedload(models.ConsumptionLog.beer).joinedload(models.Beer.brewery),
        )
        .order_by(models.ConsumptionLog.consumed_on.desc(), models.ConsumptionLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        schemas.RecentConsumedOut(
            username=log.user.username,
            display_name=log.user.display_name,
            beer_name=log.beer.name,
            brewery_name=log.beer.brewery.name,
            consumed_on=log.consumed_on,
        )
        for log in logs
    ]


@router.get("/u/{username}/trades")
def public_trades(username: str, db: Session = Depends(get_db)):
    """Shareable, no-login trade/wanted board for one user. Gated only by
    trading_enabled - deliberately independent of cellar_public, so
    someone can keep their full cellar private while still sharing just
    what they're trading or looking for."""
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.trading_enabled:
        raise HTTPException(status_code=404, detail="That trade list is private or doesn't exist.")

    def sort_key(name, brewery_name):
        return (brewery_name.lower(), name.lower()) if user.default_sort == "brewery" else (name.lower(), brewery_name.lower())

    def serialize_beer(beer):
        return {
            "id": beer.id,
            "name": beer.name,
            "style": beer.style,
            "abv": beer.abv,
            "reference_url": beer.reference_url,
            "brewery": {"id": beer.brewery.id, "name": beer.brewery.name},
        }

    entries = (
        db.query(models.CellarEntry)
        .options(joinedload(models.CellarEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.CellarEntry.user_id == user.id, models.CellarEntry.trade_status != "none")
        .all()
    )
    for_trade = [
        {"id": e.id, "quantity": e.quantity, "batch_notes": e.batch_notes, "beer": serialize_beer(e.beer)}
        for e in entries
        if e.trade_status == "ft" and e.quantity > 0
    ]
    for_trade.sort(key=lambda x: sort_key(x["beer"]["name"], x["beer"]["brewery"]["name"]))

    # "Wanted" combines two distinct things: cellar entries marked ISO (you
    # own some already but want more) and WantedEntry rows (you don't own
    # any yet) - each tagged so the page can label them differently.
    wanted = [
        {"id": f"cellar-{e.id}", "owned": True, "notes": e.batch_notes, "beer": serialize_beer(e.beer)}
        for e in entries
        if e.trade_status == "iso"
    ]
    wanted_entries = (
        db.query(models.WantedEntry)
        .options(joinedload(models.WantedEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.WantedEntry.user_id == user.id)
        .all()
    )
    wanted += [
        {"id": f"wanted-{w.id}", "owned": False, "notes": w.notes, "beer": serialize_beer(w.beer)}
        for w in wanted_entries
    ]
    wanted.sort(key=lambda x: sort_key(x["beer"]["name"], x["beer"]["brewery"]["name"]))

    return {
        "username": user.username,
        "display_name": user.display_name,
        "for_trade": for_trade,
        "wanted": wanted,
    }


@router.get("/u/{username}")
def public_cellar(username: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.cellar_public:
        raise HTTPException(status_code=404, detail="That cellar is private or doesn't exist.")

    entries = (
        db.query(models.CellarEntry)
        .options(joinedload(models.CellarEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.CellarEntry.user_id == user.id, models.CellarEntry.quantity > 0)
        .all()
    )
    # Sorting by drink-by date would leak the relative ordering of best-before
    # dates even when drinkby_public is off (which hides the dates themselves
    # in the response below) - fall back to the beer-name sort in that case.
    effective_sort = user.default_sort
    if effective_sort == "drinkby" and not user.drinkby_public:
        effective_sort = "beer"
    sort_entries(entries, effective_sort)

    def serialize(e: models.CellarEntry):
        return {
            "id": e.id,
            "location": e.location if user.show_fridge_column else "cellar",
            "custom_location": e.custom_location if user.show_location_column else None,
            "quantity": e.quantity,
            "size_oz": e.size_oz,
            "best_before": e.best_before.isoformat() if (user.drinkby_public and e.best_before) else None,
            "batch_notes": e.batch_notes if user.notes_public else None,
            "trade_status": e.trade_status if user.trading_enabled else "none",
            "beer": {
                "id": e.beer.id,
                "name": e.beer.name,
                "style": e.beer.style,
                "abv": e.beer.abv,
                "brewery": {"id": e.beer.brewery.id, "name": e.beer.brewery.name},
            },
        }

    consumed_count = (
        db.query(func.coalesce(func.sum(models.ConsumptionLog.quantity), 0))
        .filter(models.ConsumptionLog.user_id == user.id)
        .scalar()
    )

    tasting_notes = []
    if user.notes_public:
        logs = (
            db.query(models.ConsumptionLog)
            .options(joinedload(models.ConsumptionLog.beer).joinedload(models.Beer.brewery))
            .filter(models.ConsumptionLog.user_id == user.id, models.ConsumptionLog.note.isnot(None))
            .order_by(models.ConsumptionLog.consumed_on.desc())
            .limit(50)
            .all()
        )
        tasting_notes = [
            {
                "beer_name": log.beer.name,
                "brewery_name": log.beer.brewery.name,
                "consumed_on": log.consumed_on.isoformat(),
                "note": log.note,
                "rating": log.rating,
            }
            for log in logs
        ]

    return {
        "username": user.username,
        "display_name": user.display_name,
        "messaging_enabled": user.messaging_enabled,
        "trading_enabled": user.trading_enabled,
        "total_consumed": consumed_count,
        "entries": [serialize(e) for e in entries],
        "tasting_notes": tasting_notes,
    }
