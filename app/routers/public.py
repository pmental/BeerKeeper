from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/cellars", response_model=list[schemas.PublicUserOut])
def browse_cellars(db: Session = Depends(get_db)):
    users = db.query(models.User).filter(models.User.cellar_public.is_(True)).all()
    out = []
    for u in users:
        count = (
            db.query(func.coalesce(func.sum(models.CellarEntry.quantity), 0))
            .filter(models.CellarEntry.user_id == u.id)
            .scalar()
        )
        out.append(
            schemas.PublicUserOut(username=u.username, cellar_count=count, trading_enabled=u.trading_enabled)
        )
    out.sort(key=lambda p: p.username.lower())
    return out


@router.get("/recent", response_model=list[schemas.RecentConsumedOut])
def recent_activity(limit: int = 25, db: Session = Depends(get_db)):
    logs = (
        db.query(models.ConsumptionLog)
        .join(models.User)
        .join(models.Beer)
        .join(models.Brewery)
        .filter(models.User.cellar_public.is_(True))
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
    if user.default_sort == "brewery":
        entries.sort(key=lambda e: (e.beer.brewery.name.lower(), e.beer.name.lower()))
    else:
        entries.sort(key=lambda e: (e.beer.name.lower(), e.beer.brewery.name.lower()))

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
        "messaging_enabled": user.messaging_enabled,
        "trading_enabled": user.trading_enabled,
        "total_consumed": consumed_count,
        "entries": [serialize(e) for e in entries],
        "tasting_notes": tasting_notes,
    }
