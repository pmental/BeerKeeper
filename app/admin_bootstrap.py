import secrets

from sqlalchemy.orm import Session

from app import config, models
from app.auth import hash_password


def ensure_instance_settings(db: Session) -> None:
    """The instance_settings table always has exactly one row (id=1).
    Create it with defaults if it's missing - true on every fresh install,
    since the table itself is new here too."""
    if not db.query(models.InstanceSettings).filter(models.InstanceSettings.id == 1).first():
        db.add(models.InstanceSettings(id=1, registration_enabled=True))
        db.commit()


def promote_earliest_if_no_admin(db: Session) -> None:
    """If literally nobody is an admin, promote whoever registered first.
    Safe and idempotent to call anytime - a no-op once at least one admin
    exists. Called both at startup (covers an existing deployment that
    somehow lost its only admin) and right after any new account is
    created (covers a brand new deployment - the very first person to
    register or log in via OIDC becomes admin immediately, no restart
    needed, and no deployment can silently end up admin-less)."""
    has_admin = db.query(models.User).filter(models.User.is_admin.is_(True)).first()
    if has_admin:
        return
    earliest = db.query(models.User).order_by(models.User.created_at.asc(), models.User.id.asc()).first()
    if earliest:
        earliest.is_admin = True
        db.commit()


def ensure_local_user_exists(db: Session) -> None:
    """Single-user desktop mode only: guarantees exactly one local user
    (id=1) exists to act as. Its password is a random value nobody knows
    and nothing ever checks - deps.get_current_user bypasses login
    entirely in this mode - so it can never be used to sign in anywhere.
    A real, working password only ever gets attached to this account
    inside a specific exported backup file, at the person's request, if
    they choose to set one (see app/backup.py's login_password option) -
    it's never written back to this live database."""
    if db.query(models.User).filter(models.User.id == 1).first():
        return
    db.add(
        models.User(
            id=1,
            username="cellar",
            email="local@beerkeeper.app",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            is_admin=True,
            cellar_public=False,
            notes_public=False,
            drinkby_public=False,
            trading_enabled=False,
            messaging_enabled=False,
        )
    )
    db.commit()


def ensure_admin_exists(db: Session) -> None:
    """Startup-only: applies the CELLAR_ADMIN_USERNAMES recovery override
    (a manual lever, not the normal path), then falls back to promoting
    the earliest account if that still leaves zero admins."""
    if config.ADMIN_USERNAMES:
        db.query(models.User).filter(models.User.username.in_(config.ADMIN_USERNAMES)).update(
            {"is_admin": True}, synchronize_session=False
        )
        db.commit()

    promote_earliest_if_no_admin(db)

