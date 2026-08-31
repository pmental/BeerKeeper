import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app import models
from app.database import get_db
from app.deps import get_current_user
from app.routers.beers import _get_or_create_brewery
from app.uploads import read_upload_limited

router = APIRouter(prefix="/api/cellar", tags=["import-export"])

# Same constant and precision as the frontend's OZ_TO_ML (static/js/ui.js) -
# keeping these in sync matters so a size that round-trips through the UI
# and through a CSV export ends up meaning the same thing either way.
OZ_TO_ML = 29.5735295625

CSV_COLUMNS = [
    "brewery",
    "beer",
    "style",
    "abv",
    "location",
    "custom_location",
    "quantity",
    "size_oz",
    "size_ml",
    "bottle_date",
    "best_before",
    "batch_notes",
    "trade_status",
]


def _parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _resolve_size_oz(row: dict, unit_system: str) -> float | None:
    """Both size_oz and size_ml are always present on export, so an
    imported file that round-tripped through this app has both to choose
    from. Prefer whichever matches the importing user's own unit setting
    (matching what they'd see if they'd entered it by hand), but fall
    back to the other column if that one's missing or blank - handles a
    hand-edited CSV that only filled in one, or one exported by an
    install with the opposite unit setting."""
    oz_raw = (row.get("size_oz") or "").strip()
    ml_raw = (row.get("size_ml") or "").strip()
    if unit_system == "metric":
        raw, is_ml = (ml_raw, True) if ml_raw else (oz_raw, False)
    else:
        raw, is_ml = (oz_raw, False) if oz_raw else (ml_raw, True)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value / OZ_TO_ML if is_ml else value


@router.get("/export")
def export_cellar(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entries = (
        db.query(models.CellarEntry)
        .options(joinedload(models.CellarEntry.beer).joinedload(models.Beer.brewery))
        .filter(models.CellarEntry.user_id == current_user.id)
        .all()
    )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for e in entries:
        writer.writerow(
            {
                "brewery": e.beer.brewery.name,
                "beer": e.beer.name,
                "style": e.beer.style or "",
                "abv": e.beer.abv if e.beer.abv is not None else "",
                "location": e.location,
                "custom_location": e.custom_location or "",
                "quantity": e.quantity,
                "size_oz": e.size_oz if e.size_oz is not None else "",
                "size_ml": round(e.size_oz * OZ_TO_ML) if e.size_oz is not None else "",
                "bottle_date": e.bottle_date.isoformat() if e.bottle_date else "",
                "best_before": e.best_before.isoformat() if e.best_before else "",
                "batch_notes": (e.batch_notes or "").replace("\n", " "),
                "trade_status": e.trade_status,
            }
        )
    buf.seek(0)
    filename = f"{current_user.username}-cellar-{dt.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_cellar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    raw_bytes = await read_upload_limited(file, max_bytes=10 * 1024 * 1024)  # 10 MB - generous for any CSV
    raw = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    created, skipped = 0, 0
    errors = []

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        brewery_name = (row.get("brewery") or "").strip()
        beer_name = (row.get("beer") or "").strip()
        if not brewery_name or not beer_name:
            skipped += 1
            errors.append(f"Row {i}: missing brewery or beer name.")
            continue

        brewery = _get_or_create_brewery(db, None, brewery_name)
        beer = (
            db.query(models.Beer)
            .filter(models.Beer.brewery_id == brewery.id, models.Beer.name.ilike(beer_name))
            .first()
        )
        if not beer:
            abv_raw = (row.get("abv") or "").strip()
            beer = models.Beer(
                name=beer_name,
                brewery_id=brewery.id,
                style=(row.get("style") or "").strip() or None,
                abv=float(abv_raw) if abv_raw else None,
            )
            db.add(beer)
            db.flush()

        location = (row.get("location") or "cellar").strip().lower()
        if location not in ("cellar", "fridge"):
            location = "cellar"
        qty_raw = (row.get("quantity") or "1").strip()
        trade = (row.get("trade_status") or "none").strip().lower()
        if trade not in ("none", "ft", "iso"):
            trade = "none"

        entry = models.CellarEntry(
            user_id=current_user.id,
            beer_id=beer.id,
            location=location,
            custom_location=(row.get("custom_location") or "").strip() or None,
            quantity=int(qty_raw) if qty_raw.isdigit() else 1,
            size_oz=_resolve_size_oz(row, current_user.unit_system),
            bottle_date=_parse_date(row.get("bottle_date")),
            best_before=_parse_date(row.get("best_before")),
            batch_notes=(row.get("batch_notes") or "").strip() or None,
            trade_status=trade if current_user.trading_enabled else "none",
        )
        db.add(entry)
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors[:20]}
