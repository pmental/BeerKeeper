import csv
import datetime as dt
import io
import re

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.csv_utils import csv_safe
from app.database import eq_unicode, get_db
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
    """A date, or None if the cell was blank.

    Raises ValueError on a value that was filled in but isn't a date, so
    the caller reports it rather than quietly storing NULL. Silently
    dropping "2025-99-99" was the one place the importer still lost data
    without saying so, which sits badly next to it now telling you about
    every other kind of bad cell.
    """
    value = (value or "").strip()
    if not value:
        return None
    return dt.date.fromisoformat(value)


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


# --- cellar.beer import support -------------------------------------------
#
# cellar.beer (https://cellar.beer) exports a CSV with entirely different
# column names, capitalization, and a few field formats of its own - none
# of this reuses this app's own CSV_COLUMNS shape directly. Rather than a
# separate importer, a cellar.beer file is detected by its distinctive
# header row and each row is translated into this app's own row shape up
# front, so the main import loop below never needs to know or care which
# format the upload actually came from.

_CELLARBEER_SIGNATURE_COLUMNS = {"Brewery", "Beer", "In Cellar"}

# Deliberately not [\d.]+ - that matches "1.2.3", which then blows up in
# float() and aborts the whole import before the per-row validation
# layer ever sees it.
_CELLARBEER_SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ml|cl|l)\s*$", re.IGNORECASE)


def _parse_cellarbeer_size_ml(value: str | None) -> tuple[str, str | None]:
    """cellar.beer stores size as a string with a unit baked in ("750 ml",
    "1.5 l"), not a bare number the way this app's own size_ml column
    does. Returns (size_ml_as_string, warning_or_None)."""
    value = (value or "").strip()
    if not value:
        return "", None
    match = _CELLARBEER_SIZE_PATTERN.match(value)
    if not match:
        return "", f"Size '{value}' isn't a recognized format, left blank"
    amount = float(match.group(1))
    unit = match.group(2).lower()
    ml = {"ml": amount, "cl": amount * 10, "l": amount * 1000}[unit]
    return str(ml), None


def _parse_cellarbeer_date(value: str | None) -> tuple[str, str | None]:
    """cellar.beer sometimes exports a bare year ("2019") or year-month
    ("2040-07") instead of a full date, where this app's own dates are
    always complete. Anchoring to Jan 1 / the 1st of that month keeps the
    year information rather than silently dropping the whole date - but
    a guess is still a guess, so it's flagged with a warning rather than
    imported silently. Returns (iso_date_or_blank, warning_or_None)."""
    value = (value or "").strip()
    if not value:
        return "", None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value, None
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return f"{value}-01", f"'{value}' had no day, imported as the 1st of the month"
    if re.fullmatch(r"\d{4}", value):
        return f"{value}-01-01", f"'{value}' had no month or day, imported as January 1st"
    return "", f"'{value}' isn't a recognized date, left blank"


def _normalize_cellarbeer_row(row: dict) -> tuple[dict, list[str]]:
    """Translates one cellar.beer row into this app's own CSV_COLUMNS
    shape. cellar.beer has no cellar/fridge concept at all - just one
    free-text location - so every row imports into "cellar", with that
    free-text value going into custom_location instead."""
    warnings = []

    size_ml, size_warning = _parse_cellarbeer_size_ml(row.get("Size"))
    if size_warning:
        warnings.append(size_warning)

    bottle_date, bottle_warning = _parse_cellarbeer_date(row.get("Bottle Date"))
    if bottle_warning:
        warnings.append(f"Bottle Date {bottle_warning}")

    best_before, best_before_warning = _parse_cellarbeer_date(row.get("Drink By"))
    if best_before_warning:
        warnings.append(f"Drink By {best_before_warning}")

    normalized = {
        "brewery": row.get("Brewery", ""),
        "beer": row.get("Beer", ""),
        "style": row.get("Style", ""),
        "abv": "",
        "location": "cellar",
        "custom_location": row.get("Location", ""),
        "quantity": row.get("In Cellar", ""),
        "size_oz": "",
        "size_ml": size_ml,
        "bottle_date": bottle_date,
        "best_before": best_before,
        "batch_notes": row.get("Notes", ""),
        "trade_status": "",
    }
    return normalized, warnings


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
                "brewery": csv_safe(e.beer.brewery.name),
                "beer": csv_safe(e.beer.name),
                "style": csv_safe(e.beer.style or ""),
                "abv": e.beer.abv if e.beer.abv is not None else "",
                "location": e.location,
                "custom_location": csv_safe(e.custom_location or ""),
                "quantity": e.quantity,
                "size_oz": e.size_oz if e.size_oz is not None else "",
                "size_ml": round(e.size_oz * OZ_TO_ML) if e.size_oz is not None else "",
                "bottle_date": e.bottle_date.isoformat() if e.bottle_date else "",
                "best_before": e.best_before.isoformat() if e.best_before else "",
                "batch_notes": csv_safe((e.batch_notes or "").replace("\n", " ")),
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


def _parse_date_labelled(value: str, column: str):
    try:
        return _parse_date(value)
    except ValueError:
        raise ValueError(f"{column}: '{(value or '').strip()}' isn't a valid date (expected YYYY-MM-DD)")


def _validated_row(row: dict, unit_system: str) -> "tuple[schemas.CellarEntryIn | None, str | None]":
    """Put one CSV row through the same schemas the API uses.

    The importer used to do its own parsing, which meant a file could
    carry values the API would refuse: an ABV of 9999, a 50,000-character
    note, a quantity of a billion. Worse, a non-numeric ABV raised
    straight out of float() and took the whole import down with it,
    losing the rows that had already been read.

    Building the same Pydantic models the JSON endpoints use keeps one
    set of rules rather than two that can drift apart, and turns a bad
    row into a skipped row with a readable reason.
    """
    qty_raw = (row.get("quantity") or "1").strip()
    abv_raw = (row.get("abv") or "").strip()
    size_oz = _resolve_size_oz(row, unit_system)

    try:
        beer = schemas.BeerIn(
            name=(row.get("beer") or "").strip(),
            new_brewery_name=(row.get("brewery") or "").strip(),
            style=(row.get("style") or "").strip() or None,
            abv=float(abv_raw) if abv_raw else None,
        )
        entry = schemas.CellarEntryIn(
            beer=beer,
            location=(row.get("location") or "cellar").strip().lower(),
            custom_location=(row.get("custom_location") or "").strip() or None,
            quantity=int(qty_raw) if qty_raw else 1,
            size_oz=size_oz,
            bottle_date=_parse_date_labelled(row.get("bottle_date"), "bottle_date"),
            best_before=_parse_date_labelled(row.get("best_before"), "best_before"),
            batch_notes=(row.get("batch_notes") or "").strip() or None,
            trade_status=(row.get("trade_status") or "none").strip().lower(),
        )
    except ValueError as e:
        # Covers both Pydantic's ValidationError and a plain float()/int()
        # failure on a field that isn't a number at all.
        return None, _first_validation_message(e)
    return entry, None


def _first_validation_message(e: Exception) -> str:
    """One readable line out of a validation failure, rather than the
    multi-line dump Pydantic produces."""
    errors = getattr(e, "errors", None)
    if callable(errors):
        try:
            first = errors()[0]
            field = ".".join(str(p) for p in first.get("loc", ()) if p != "beer")
            return f"{field or 'row'}: {first.get('msg', 'invalid value')}"
        except Exception:  # noqa: BLE001
            pass
    return str(e).splitlines()[0]


@router.post("/import")
async def import_cellar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    raw_bytes = await read_upload_limited(file, max_bytes=10 * 1024 * 1024)  # 10 MB - generous for any CSV
    raw = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    # A cellar.beer export uses distinctly different, Title-Case column
    # names from this app's own format - a few of its most distinctive
    # ones being present is a reliable enough signal to tell the two
    # apart, so "Import CSV" can just handle either without the user
    # needing to know or pick which format they have.
    is_cellarbeer = _CELLARBEER_SIGNATURE_COLUMNS.issubset(set(reader.fieldnames or []))
    created, skipped = 0, 0
    errors = []

    for i, raw_row in enumerate(reader, start=2):  # row 1 is the header
        if is_cellarbeer:
            row, row_warnings = _normalize_cellarbeer_row(raw_row)
            errors.extend(f"Row {i}: {w}" for w in row_warnings)
        else:
            row = raw_row

        brewery_name = (row.get("brewery") or "").strip()
        beer_name = (row.get("beer") or "").strip()
        if not brewery_name or not beer_name:
            skipped += 1
            errors.append(f"Row {i}: missing brewery or beer name.")
            continue

        valid, problem = _validated_row(row, current_user.unit_system)
        if valid is None:
            skipped += 1
            errors.append(f"Row {i}: {problem}")
            continue

        brewery = _get_or_create_brewery(db, None, brewery_name)
        beer = (
            db.query(models.Beer)
            .filter(models.Beer.brewery_id == brewery.id, eq_unicode(models.Beer.name, beer_name))
            .first()
        )
        if not beer:
            beer = models.Beer(
                name=valid.beer.name,
                brewery_id=brewery.id,
                style=valid.beer.style,
                abv=valid.beer.abv,
            )
            db.add(beer)
            db.flush()

        entry = models.CellarEntry(
            user_id=current_user.id,
            beer_id=beer.id,
            location=valid.location,
            custom_location=valid.custom_location,
            quantity=valid.quantity,
            size_oz=valid.size_oz,
            bottle_date=valid.bottle_date,
            best_before=valid.best_before,
            batch_notes=valid.batch_notes,
            trade_status=valid.trade_status if current_user.trading_enabled else "none",
        )
        db.add(entry)
        created += 1

    db.commit()
    return {"created": created, "skipped": skipped, "errors": errors[:20]}
