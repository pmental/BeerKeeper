"""Drink-by reminders.

One sweep finds bottles coming due and fans them out to whichever
channels a user has turned on. Email is an account preference; push is
per device. Both are opt-in and both are off until someone asks for them.

Everything here is deliberately conservative about sending twice: each
entry carries a drinkby_notified_at stamp, set once a reminder covering
it has gone out, so the daily run doesn't repeat itself. The stamp lives
on the entry, so drinking or deleting the bottle takes it with them.
"""

import asyncio
import datetime as dt
import logging

from sqlalchemy.orm import Session, joinedload

from app import models
from app.database import SessionLocal
from app.email import is_smtp_enabled, send_email
from app.push import send_push

log = logging.getLogger("cellar.notifications")

# How often the loop wakes up. The sweep itself is idempotent per day, so
# waking more often than daily costs nothing and means a server that
# isn't up at midnight still sends within a few hours.
_SWEEP_INTERVAL_SECONDS = 6 * 60 * 60


def find_due_entries(db: Session, user: models.User):
    """Bottles of this user's that are coming due and haven't been
    flagged yet. Excludes empty entries - a row at quantity 0 is
    bookkeeping (a wanted-list marker), not something to drink."""
    cutoff = dt.date.today() + dt.timedelta(days=user.notify_days_ahead)
    return (
        db.query(models.CellarEntry)
        .options(joinedload(models.CellarEntry.beer).joinedload(models.Beer.brewery))
        .filter(
            models.CellarEntry.user_id == user.id,
            models.CellarEntry.best_before.isnot(None),
            models.CellarEntry.best_before <= cutoff,
            models.CellarEntry.quantity > 0,
            models.CellarEntry.drinkby_notified_at.is_(None),
        )
        .order_by(models.CellarEntry.best_before)
        .all()
    )


def _describe(entries) -> str:
    lines = []
    for e in entries:
        qty = f"{e.quantity} x " if e.quantity > 1 else ""
        lines.append(f"- {qty}{e.beer.brewery.name} {e.beer.name} (drink by {e.best_before.isoformat()})")
    return "\n".join(lines)


def _send_email(user: models.User, entries) -> bool:
    """Returns whether the mail actually went out.

    Uses send_email directly rather than send_email_safely: the "safely"
    variant swallows failures and returns nothing, which is right for
    fire-and-forget background sends but useless here, where the whole
    point is knowing whether the reminder landed.
    """
    n = len(entries)
    subject = f"{n} bottle{'' if n == 1 else 's'} coming due in your cellar"
    body = (
        f"Hi {user.username},\n\n"
        f"{'This bottle is' if n == 1 else 'These bottles are'} approaching "
        f"{'its' if n == 1 else 'their'} drink-by date:\n\n"
        f"{_describe(entries)}\n\n"
        "You're getting this because drink-by reminders are switched on for "
        "your account. Turn them off any time on the Account page.\n"
    )
    try:
        send_email(user.email, subject, body)
        return True
    except Exception as e:  # noqa: BLE001 - a bad send shouldn't stop the sweep
        log.warning("Drink-by email to %s failed: %s", user.email, e)
        return False


def _send_push(db: Session, user: models.User, entries) -> bool:
    """Returns whether at least one device actually received it.

    A dead endpoint is dropped, but dropping it isn't delivery - if every
    device is gone or erroring, this reports False so the reminder stays
    unsent and is tried again next sweep.
    """
    n = len(entries)
    first = entries[0]
    title = f"{n} bottle{'' if n == 1 else 's'} coming due"
    if n == 1:
        body = f"{first.beer.brewery.name} {first.beer.name} - drink by {first.best_before.isoformat()}"
    else:
        body = f"{first.beer.brewery.name} {first.beer.name} and {n - 1} more"

    payload = {"title": title, "body": body, "url": "/#/cellar"}

    any_sent = False
    for sub in list(user.push_subscriptions):
        result = send_push(
            {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            payload,
        )
        if result == "sent":
            any_sent = True
        elif result == "gone":
            log.info("Dropping expired push subscription %s", sub.id)
            db.delete(sub)
    return any_sent


def run_sweep(db: Session, now: "dt.datetime | None" = None) -> dict:
    """Find due bottles for every opted-in user and notify them.

    Returns a small summary, which is what makes this testable without
    actually delivering anything.
    """
    now = now or dt.datetime.utcnow()
    summary = {"users_notified": 0, "entries_flagged": 0, "emails": 0, "push_devices": 0, "undelivered": 0}

    smtp_ready = is_smtp_enabled(db)

    users = (
        db.query(models.User)
        .options(joinedload(models.User.push_subscriptions))
        .filter(
            (models.User.notify_drinkby_email.is_(True))
            | (models.User.push_subscriptions.any())
        )
        .all()
    )

    for user in users:
        entries = find_due_entries(db, user)
        if not entries:
            continue

        wants_email = user.notify_drinkby_email and smtp_ready and user.email
        devices = list(user.push_subscriptions)

        if not wants_email and not devices:
            continue

        delivered = False

        if wants_email:
            if _send_email(user, entries):
                summary["emails"] += 1
                delivered = True
        if devices:
            if _send_push(db, user, entries):
                summary["push_devices"] += len(devices)
                delivered = True

        if not delivered:
            # Nothing actually reached this user, so the reminder stays
            # unsent and the next sweep tries again. Marking it here would
            # mean a push service being briefly unreachable, or SMTP being
            # misconfigured, silently costs someone the only warning they
            # were going to get about a bottle going over.
            summary["undelivered"] += 1
            continue

        for e in entries:
            e.drinkby_notified_at = now
        summary["entries_flagged"] += len(entries)
        summary["users_notified"] += 1

    db.commit()
    return summary


async def sweep_loop() -> None:
    """Background loop started at app startup.

    Deliberately a plain asyncio task rather than a scheduler dependency:
    this app runs as a single uvicorn process, and a loop that dies with
    the app is easier to reason about than a parallel scheduler with its
    own lifecycle. If it's ever run with multiple workers, this wants
    replacing with an external cron hitting an authenticated endpoint,
    or each worker will sweep independently.
    """
    while True:
        try:
            db = SessionLocal()
            try:
                summary = run_sweep(db)
                if summary["users_notified"]:
                    log.info("Drink-by sweep: %s", summary)
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001 - the loop must outlive any single failure
            log.warning("Drink-by sweep failed: %s", e)
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
