from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models, push
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api/push", tags=["push"])


def _validate_endpoint(raw: str) -> str:
    """Reject anything that isn't plausibly a browser push service.

    The check itself lives in app/push.py, because it's applied again
    just before each send rather than only here - see the note there on
    what it does and doesn't protect against.
    """
    reason = push.endpoint_rejection_reason(raw)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    return raw


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=255)
    auth: str = Field(max_length=255)


class SubscribeIn(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: PushKeys
    user_agent: "str | None" = Field(default=None, max_length=255)


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(max_length=2048)


@router.get("/key")
def vapid_key(_user: models.User = Depends(get_current_user)):
    """The application server key a browser needs to subscribe.

    Behind auth like the rest of the API: there's no reason for a logged
    out visitor to need it, since subscribing requires an account to
    attach the subscription to.
    """
    return {"key": push.public_key_b64()}


@router.post("/subscribe")
def subscribe(
    payload: SubscribeIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    endpoint = _validate_endpoint(payload.endpoint)
    existing = (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.endpoint == endpoint)
        .first()
    )
    if existing:
        # Same browser re-subscribing, possibly as a different user on a
        # shared device: refresh the keys and hand the row to whoever is
        # logged in now rather than leaving it pointing at the old owner.
        existing.user_id = current_user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        existing.user_agent = payload.user_agent
    else:
        db.add(
            models.PushSubscription(
                user_id=current_user.id,
                endpoint=endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
                user_agent=payload.user_agent,
            )
        )
    db.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(
    payload: UnsubscribeIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    (
        db.query(models.PushSubscription)
        .filter(
            models.PushSubscription.endpoint == payload.endpoint,
            models.PushSubscription.user_id == current_user.id,
        )
        .delete()
    )
    db.commit()
    return {"ok": True}


@router.get("/status")
def status(
    endpoint: "str | None" = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """How many devices this account has push enabled on, and whether the
    endpoint the caller passed is one of them.

    The second part lets the account page tell the difference between "this
    browser is subscribed" and "this browser has a leftover subscription the
    server doesn't know about" - which is what you're left with if the row
    was pruned as expired, or removed on another device.
    """
    q = db.query(models.PushSubscription).filter(
        models.PushSubscription.user_id == current_user.id
    )
    known = False
    if endpoint:
        known = q.filter(models.PushSubscription.endpoint == endpoint).first() is not None
    return {"devices": q.count(), "this_device": known}
