import csv
import datetime as dt
import io

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import backup, config, models, schemas
from app.auth import hash_password
from app.database import get_db, ilike_unicode
from app.deps import require_admin
from app.crypto import encrypt_secret
from app.email import resolve_smtp_settings, send_test_email, send_welcome_email
from app.routers.beers import _get_or_create_brewery
from app.uploads import read_upload_limited
from app.url_utils import sanitize_url

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _get_settings(db: Session) -> models.InstanceSettings:
    settings = db.query(models.InstanceSettings).filter(models.InstanceSettings.id == 1).first()
    if not settings:
        settings = models.InstanceSettings(id=1, registration_enabled=True)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _serialize_settings(db: Session, settings: models.InstanceSettings) -> schemas.InstanceSettingsOut:
    resolved = resolve_smtp_settings(db)
    return schemas.InstanceSettingsOut(
        registration_enabled=settings.registration_enabled,
        password_auth_enabled=config.PASSWORD_AUTH_ENABLED,
        oidc_enabled=config.OIDC_ENABLED,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_security=settings.smtp_security,
        smtp_username=settings.smtp_username,
        smtp_password_set=bool(resolved.password),
        smtp_from_email=settings.smtp_from_email,
        smtp_from_name=settings.smtp_from_name,
        smtp_skip_cert_verify=settings.smtp_skip_cert_verify,
        smtp_enabled=resolved.enabled,
        smtp_effective_summary=f"{resolved.host}:{resolved.port} via {resolved.security}" if resolved.enabled else None,
    )


def _serialize_user(db: Session, user: models.User) -> schemas.AdminUserOut:
    cellar_count = (
        db.query(func.coalesce(func.sum(models.CellarEntry.quantity), 0))
        .filter(models.CellarEntry.user_id == user.id)
        .scalar()
    )
    return schemas.AdminUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        is_admin=user.is_admin,
        has_oidc=user.oidc_subject is not None,
        created_at=user.created_at,
        cellar_count=cellar_count,
    )


@router.get("/settings", response_model=schemas.InstanceSettingsOut)
def get_settings(db: Session = Depends(get_db), _admin: models.User = Depends(require_admin)):
    return _serialize_settings(db, _get_settings(db))


@router.patch("/settings", response_model=schemas.InstanceSettingsOut)
def patch_settings(
    payload: schemas.InstanceSettingsPatch,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    settings = _get_settings(db)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        # Blank string in a text field means "clear the override, fall
        # back to the env var" - store as NULL, not "". The frontend is
        # responsible for only including smtp_password in the request at
        # all when actually setting or deliberately clearing it (it's
        # never round-tripped back for display, so "leave it blank" while
        # editing something else must NOT wipe an already-stored one).
        if isinstance(value, str) and value == "":
            value = None
        if field == "smtp_password" and value:
            value = encrypt_secret(value)
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return _serialize_settings(db, settings)


@router.post("/settings/smtp/test")
def test_smtp(
    payload: schemas.SmtpTestIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    try:
        send_test_email(payload.to_email)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't send: {type(e).__name__}: {e}"[:300])
    return {"ok": True}


@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_users(db: Session = Depends(get_db), _admin: models.User = Depends(require_admin)):
    users = db.query(models.User).order_by(models.User.username.asc()).all()
    return [_serialize_user(db, u) for u in users]


@router.post("/users", response_model=schemas.AdminUserOut)
def create_user(
    payload: schemas.AdminUserCreateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    user = models.User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That username or email is already taken.")
    db.refresh(user)
    if payload.send_welcome_email and resolve_smtp_settings(db).enabled:
        background_tasks.add_task(send_welcome_email, user.email, user.username)
    return _serialize_user(db, user)


def _admin_count(db: Session) -> int:
    return db.query(models.User).filter(models.User.is_admin.is_(True)).count()


@router.patch("/users/{user_id}", response_model=schemas.AdminUserOut)
def patch_user(
    user_id: int,
    payload: schemas.AdminUserPatch,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    data = payload.model_dump(exclude_unset=True)
    if "is_admin" in data and data["is_admin"] is False and user.is_admin:
        if _admin_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Can't remove the last admin.")

    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return _serialize_user(db, user)


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: schemas.AdminPasswordResetIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.password_hash = hash_password(payload.new_password)
    # Also invalidate any of their existing sessions - a plausible reason
    # an admin is resetting someone else's password is a suspected
    # compromise, and leaving old tokens valid would defeat the point.
    user.token_valid_after = dt.datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account from here.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_admin and _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="Can't delete the last admin.")

    db.delete(user)
    db.commit()
    return {"ok": True}


@router.get("/backup")
def download_backup(_admin: models.User = Depends(require_admin)):
    """A single-file snapshot of the entire instance - every user, cellar
    entry, beer, brewery, and beer style - not just one account's data
    (unlike Import/Export's CSV, which is per-user). Meant for moving a
    whole instance to a new install."""
    data = backup.create_backup_bytes()
    filename = f"beerkeeper-backup-{dt.date.today().isoformat()}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/restore")
def get_restore_status(_admin: models.User = Depends(require_admin)):
    return {"pending": backup.has_pending_restore()}


@router.post("/restore")
async def upload_restore(file: UploadFile = File(...), _admin: models.User = Depends(require_admin)):
    """Validates and stages a restore - does NOT apply it immediately.
    See app/backup.py for why: swapping the live database file out from
    under active connections is exactly the kind of thing that corrupts
    data, so the actual swap happens at the next clean startup instead."""
    data = await read_upload_limited(file, max_bytes=200 * 1024 * 1024)  # 200 MB - generous for db + styles
    try:
        backup.stage_restore(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"pending": True}


@router.delete("/restore")
def cancel_restore(_admin: models.User = Depends(require_admin)):
    cancelled = backup.cancel_pending_restore()
    return {"pending": False, "cancelled": cancelled}


def _serialize_brewery(brewery: models.Brewery, beer_count: int) -> schemas.AdminBreweryOut:
    return schemas.AdminBreweryOut(id=brewery.id, name=brewery.name, website=brewery.website, beer_count=beer_count)


@router.get("/breweries", response_model=list[schemas.AdminBreweryOut])
def list_breweries_admin(
    q: str = "",
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    query = (
        db.query(models.Brewery, func.count(models.Beer.id))
        .outerjoin(models.Beer, models.Beer.brewery_id == models.Brewery.id)
        .group_by(models.Brewery.id)
    )
    if q:
        query = query.filter(ilike_unicode(models.Brewery.name, f"%{q}%"))
    rows = query.order_by(models.Brewery.name).limit(200).all()
    return [_serialize_brewery(b, count) for b, count in rows]


@router.post("/breweries", response_model=schemas.AdminBreweryOut)
def create_brewery_admin(
    payload: schemas.BreweryIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    existing = db.query(models.Brewery).filter(ilike_unicode(models.Brewery.name, payload.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="A brewery with that name already exists.")
    brewery = models.Brewery(name=payload.name.strip(), website=sanitize_url(payload.website))
    db.add(brewery)
    db.commit()
    db.refresh(brewery)
    return _serialize_brewery(brewery, 0)


@router.patch("/breweries/{brewery_id}", response_model=schemas.AdminBreweryOut)
def update_brewery_admin(
    brewery_id: int,
    payload: schemas.AdminBreweryPatch,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    brewery = db.query(models.Brewery).filter(models.Brewery.id == brewery_id).first()
    if not brewery:
        raise HTTPException(status_code=404, detail="Brewery not found.")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        new_name = (data["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Name can't be empty.")
        dupe = (
            db.query(models.Brewery)
            .filter(ilike_unicode(models.Brewery.name, new_name), models.Brewery.id != brewery_id)
            .first()
        )
        if dupe:
            raise HTTPException(status_code=400, detail="Another brewery already has that name.")
        brewery.name = new_name
    if "website" in data:
        brewery.website = sanitize_url(data["website"])

    db.commit()
    db.refresh(brewery)
    beer_count = db.query(func.count(models.Beer.id)).filter(models.Beer.brewery_id == brewery.id).scalar()
    return _serialize_brewery(brewery, beer_count)


@router.delete("/breweries/{brewery_id}")
def delete_brewery_admin(
    brewery_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    brewery = db.query(models.Brewery).filter(models.Brewery.id == brewery_id).first()
    if not brewery:
        raise HTTPException(status_code=404, detail="Brewery not found.")
    beer_count = db.query(func.count(models.Beer.id)).filter(models.Beer.brewery_id == brewery.id).scalar()
    if beer_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Can't delete - {beer_count} beer{'s' if beer_count != 1 else ''} still reference this "
                "brewery. Delete or reassign them first."
            ),
        )
    db.delete(brewery)
    db.commit()
    return {"ok": True}


@router.get("/breweries/export")
def export_breweries_admin(db: Session = Depends(get_db), _admin: models.User = Depends(require_admin)):
    breweries = db.query(models.Brewery).order_by(models.Brewery.name).all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "website"])
    writer.writeheader()
    for b in breweries:
        writer.writerow({"name": b.name, "website": b.website or ""})
    buf.seek(0)
    filename = f"breweries-{dt.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/breweries/import", response_model=schemas.AdminBreweryImportResult)
async def import_breweries_admin(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    raw_bytes = await read_upload_limited(file, max_bytes=5 * 1024 * 1024)  # 5 MB - generous for a brewery list
    raw = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    created, skipped = 0, 0
    errors = []

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            errors.append(f"Row {i}: missing name.")
            continue
        existing = db.query(models.Brewery).filter(ilike_unicode(models.Brewery.name, name)).first()
        if existing:
            skipped += 1
            continue
        website = sanitize_url(row.get("website"))
        db.add(models.Brewery(name=name, website=website))
        created += 1

    db.commit()
    return schemas.AdminBreweryImportResult(created=created, skipped=skipped, errors=errors[:20])


def _beer_usage_count(db: Session, beer_id: int) -> int:
    """A beer can be referenced from three different tables - cellar
    entries, tasting history, and wanted-list rows - so "is this beer in
    use" has to check all three, not just cellar entries."""
    cellar = db.query(func.count(models.CellarEntry.id)).filter(models.CellarEntry.beer_id == beer_id).scalar()
    logs = db.query(func.count(models.ConsumptionLog.id)).filter(models.ConsumptionLog.beer_id == beer_id).scalar()
    wanted = db.query(func.count(models.WantedEntry.id)).filter(models.WantedEntry.beer_id == beer_id).scalar()
    return cellar + logs + wanted


def _beer_usage_counts(db: Session, beer_ids: list[int]) -> dict[int, int]:
    """Same as _beer_usage_count() above, but for many beers in one go -
    three aggregated GROUP BY queries total instead of three queries per
    beer, so rendering a page of the admin beer list doesn't turn into
    hundreds of individual round trips."""
    counts: dict[int, int] = {bid: 0 for bid in beer_ids}
    if not beer_ids:
        return counts
    for model in (models.CellarEntry, models.ConsumptionLog, models.WantedEntry):
        rows = (
            db.query(model.beer_id, func.count(model.id))
            .filter(model.beer_id.in_(beer_ids))
            .group_by(model.beer_id)
            .all()
        )
        for beer_id, count in rows:
            counts[beer_id] += count
    return counts


def _serialize_beer(beer: models.Beer, usage_count: int) -> schemas.AdminBeerOut:
    return schemas.AdminBeerOut(
        id=beer.id,
        name=beer.name,
        style=beer.style,
        abv=beer.abv,
        reference_url=beer.reference_url,
        brewery=beer.brewery,
        usage_count=usage_count,
    )


@router.get("/beers", response_model=list[schemas.AdminBeerOut])
def list_beers_admin(
    q: str = "",
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    query = db.query(models.Beer).options(joinedload(models.Beer.brewery))
    if q:
        query = query.join(models.Brewery).filter(
            or_(ilike_unicode(models.Beer.name, f"%{q}%"), ilike_unicode(models.Brewery.name, f"%{q}%"))
        )
    beers = query.order_by(models.Beer.name).limit(200).all()
    usage_counts = _beer_usage_counts(db, [b.id for b in beers])
    return [_serialize_beer(b, usage_counts.get(b.id, 0)) for b in beers]


@router.post("/beers", response_model=schemas.AdminBeerOut)
def create_beer_admin(
    payload: schemas.AdminBeerIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    brewery = db.query(models.Brewery).filter(models.Brewery.id == payload.brewery_id).first()
    if not brewery:
        raise HTTPException(status_code=404, detail="Brewery not found.")
    existing = (
        db.query(models.Beer)
        .filter(models.Beer.brewery_id == payload.brewery_id, ilike_unicode(models.Beer.name, payload.name))
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="That brewery already has a beer with that name.")
    beer = models.Beer(
        name=payload.name.strip(),
        brewery_id=payload.brewery_id,
        style=(payload.style or "").strip() or None,
        abv=payload.abv,
        reference_url=sanitize_url(payload.reference_url),
    )
    db.add(beer)
    db.commit()
    db.refresh(beer)
    return _serialize_beer(beer, 0)


@router.patch("/beers/{beer_id}", response_model=schemas.AdminBeerOut)
def update_beer_admin(
    beer_id: int,
    payload: schemas.AdminBeerPatch,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    beer = db.query(models.Beer).filter(models.Beer.id == beer_id).first()
    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found.")

    data = payload.model_dump(exclude_unset=True)
    new_name = data["name"].strip() if "name" in data and data["name"] else beer.name
    new_brewery_id = data.get("brewery_id", beer.brewery_id)
    if "brewery_id" in data:
        if not db.query(models.Brewery).filter(models.Brewery.id == new_brewery_id).first():
            raise HTTPException(status_code=404, detail="Brewery not found.")
    if "name" in data or "brewery_id" in data:
        dupe = (
            db.query(models.Beer)
            .filter(
                models.Beer.brewery_id == new_brewery_id,
                ilike_unicode(models.Beer.name, new_name),
                models.Beer.id != beer_id,
            )
            .first()
        )
        if dupe:
            raise HTTPException(status_code=400, detail="That brewery already has a beer with that name.")

    if "name" in data:
        beer.name = new_name
    if "brewery_id" in data:
        beer.brewery_id = new_brewery_id
    if "style" in data:
        beer.style = (data["style"] or "").strip() or None
    if "abv" in data:
        beer.abv = data["abv"]
    if "reference_url" in data:
        beer.reference_url = sanitize_url(data["reference_url"])

    db.commit()
    db.refresh(beer)
    return _serialize_beer(beer, _beer_usage_count(db, beer.id))


@router.delete("/beers/{beer_id}")
def delete_beer_admin(
    beer_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    beer = db.query(models.Beer).filter(models.Beer.id == beer_id).first()
    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found.")
    usage = _beer_usage_count(db, beer_id)
    if usage:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Can't delete - {usage} cellar/history/wanted entr{'y' if usage == 1 else 'ies'} still "
                "reference this beer. Delete or reassign them first."
            ),
        )
    db.delete(beer)
    db.commit()
    return {"ok": True}


@router.get("/beers/export")
def export_beers_admin(db: Session = Depends(get_db), _admin: models.User = Depends(require_admin)):
    beers = db.query(models.Beer).options(joinedload(models.Beer.brewery)).order_by(models.Beer.name).all()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "brewery", "style", "abv", "reference_url"])
    writer.writeheader()
    for b in beers:
        writer.writerow(
            {
                "name": b.name,
                "brewery": b.brewery.name,
                "style": b.style or "",
                "abv": b.abv if b.abv is not None else "",
                "reference_url": b.reference_url or "",
            }
        )
    buf.seek(0)
    filename = f"beers-{dt.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/beers/import", response_model=schemas.AdminBreweryImportResult)
async def import_beers_admin(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    raw_bytes = await read_upload_limited(file, max_bytes=5 * 1024 * 1024)
    raw = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    created, skipped = 0, 0
    errors = []

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        name = (row.get("name") or "").strip()
        brewery_name = (row.get("brewery") or "").strip()
        if not name or not brewery_name:
            skipped += 1
            errors.append(f"Row {i}: missing name or brewery.")
            continue
        brewery = _get_or_create_brewery(db, None, brewery_name)
        existing = (
            db.query(models.Beer)
            .filter(models.Beer.brewery_id == brewery.id, ilike_unicode(models.Beer.name, name))
            .first()
        )
        if existing:
            skipped += 1
            continue
        abv_raw = (row.get("abv") or "").strip()
        db.add(
            models.Beer(
                name=name,
                brewery_id=brewery.id,
                style=(row.get("style") or "").strip() or None,
                abv=float(abv_raw) if abv_raw else None,
                reference_url=sanitize_url(row.get("reference_url")),
            )
        )
        created += 1

    db.commit()
    return schemas.AdminBreweryImportResult(created=created, skipped=skipped, errors=errors[:20])


@router.get("/beer-styles", response_model=list[schemas.AdminBeerStyleOut])
def list_beer_styles_admin(
    q: str = "",
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    query = db.query(models.BeerStyle)
    if q:
        query = query.filter(ilike_unicode(models.BeerStyle.name, f"%{q}%"))
    # Alphabetical here, unlike the public autocomplete's preserved
    # category order (see beer_styles.py) - finding a specific style to
    # edit or delete matters more here than browsing by category.
    return query.order_by(models.BeerStyle.name).limit(200).all()


@router.post("/beer-styles", response_model=schemas.AdminBeerStyleOut)
def create_beer_style_admin(
    payload: schemas.AdminBeerStyleIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    existing = db.query(models.BeerStyle).filter(ilike_unicode(models.BeerStyle.name, payload.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="That style already exists.")
    # New styles go at the end of the (otherwise category-grouped)
    # public suggestion list, rather than needing a real position picked.
    next_order = (db.query(func.max(models.BeerStyle.sort_order)).scalar() or 0) + 1
    style = models.BeerStyle(name=payload.name.strip(), sort_order=next_order)
    db.add(style)
    db.commit()
    db.refresh(style)
    return style


@router.patch("/beer-styles/{style_id}", response_model=schemas.AdminBeerStyleOut)
def update_beer_style_admin(
    style_id: int,
    payload: schemas.AdminBeerStylePatch,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    style = db.query(models.BeerStyle).filter(models.BeerStyle.id == style_id).first()
    if not style:
        raise HTTPException(status_code=404, detail="Style not found.")
    new_name = payload.name.strip()
    dupe = (
        db.query(models.BeerStyle)
        .filter(ilike_unicode(models.BeerStyle.name, new_name), models.BeerStyle.id != style_id)
        .first()
    )
    if dupe:
        raise HTTPException(status_code=400, detail="Another style already has that name.")
    style.name = new_name
    db.commit()
    db.refresh(style)
    return style


@router.delete("/beer-styles/{style_id}")
def delete_beer_style_admin(
    style_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    # No usage-blocking check here, unlike breweries/beers - style is (and
    # always has been) a free-text field on Beer, never a foreign key
    # into this table, so nothing actually references a style row by ID.
    style = db.query(models.BeerStyle).filter(models.BeerStyle.id == style_id).first()
    if not style:
        raise HTTPException(status_code=404, detail="Style not found.")
    db.delete(style)
    db.commit()
    return {"ok": True}
