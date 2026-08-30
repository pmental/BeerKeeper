import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import backup, config, models, schemas
from app.auth import hash_password
from app.database import get_db
from app.deps import require_admin
from app.email import resolve_smtp_settings, send_test_email, send_welcome_email
from app.uploads import read_upload_limited

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
    admin: models.User = Depends(require_admin),
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
    entry, beer, brewery, and your custom beer_styles.txt (which lives
    outside the database, so it's zipped alongside it rather than
    silently left out) - not just one account's data (unlike
    Import/Export's CSV, which is per-user). Meant for moving a whole
    instance to a new install."""
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
