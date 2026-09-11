"""Web push delivery.

A VAPID keypair identifies this server to the browser vendors' push
services (FCM, Mozilla autopush, Apple). It has to stay stable: the
public half is baked into every subscription a browser creates, so
regenerating it silently invalidates every existing subscription. It's
therefore generated once and kept in the data directory alongside the
secret key, with the same 0600 permissions - it's a signing key.
"""

import base64
import ipaddress
import json
import logging
import os
import socket
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

from app.database import DATA_DIR

log = logging.getLogger("cellar.push")

_VAPID_KEY_FILE = os.path.join(DATA_DIR, ".vapid_private.pem")

# Push services want a contact for the application server, so they have
# someone to reach about a misbehaving sender. mailto: with no real
# address is accepted and avoids inventing one.
_VAPID_CLAIM_SUB = os.environ.get("CELLAR_VAPID_SUBJECT", "mailto:admin@localhost")

_vapid_cache: "Vapid01 | None" = None


def _load_or_create_vapid() -> Vapid01:
    global _vapid_cache
    if _vapid_cache is not None:
        return _vapid_cache

    if os.path.exists(_VAPID_KEY_FILE):
        v = Vapid01.from_file(_VAPID_KEY_FILE)
    else:
        v = Vapid01()
        v.generate_keys()
        os.makedirs(os.path.dirname(_VAPID_KEY_FILE), exist_ok=True)
        # Written via os.open so the mode applies from creation rather
        # than depending on the process umask - same reasoning as the
        # app's secret key file.
        fd = os.open(_VAPID_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
        v.save_key(_VAPID_KEY_FILE)
        os.chmod(_VAPID_KEY_FILE, 0o600)
        log.info("Generated a new VAPID keypair for web push.")

    _vapid_cache = v
    return v


def public_key_b64() -> str:
    """The application server key the browser needs when subscribing."""
    v = _load_or_create_vapid()
    raw = v.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def endpoint_rejection_reason(raw: str) -> "str | None":
    """None if this endpoint looks safe to send to, else why not.

    The endpoint comes from the client and the sweep later makes an
    outbound request to it, so without a check an authenticated user
    could point it at anything the server can reach - an internal
    service, a cloud metadata address - and use the reminder sweep as a
    request proxy. Requiring HTTPS alone isn't enough, since https:// to
    an internal host works just as well, so the host is resolved and
    non-public addresses are refused.

    Deliberately not an allowlist of vendor hostnames: browser vendors
    move their push infrastructure, and a stale allowlist would silently
    break subscriptions for real users.

    Worth being honest about what this does and doesn't cover. It's
    checked both when subscribing and again immediately before each send,
    so a host that later starts resolving to an internal address stops
    being delivered to. It does not close the gap entirely: the push
    library resolves the name again itself when it opens the connection,
    so a DNS record flipped in the moment between this check and that one
    would still get through. Closing that properly means validating the
    IP the connection actually goes to, which needs control of the socket
    that pywebpush owns.
    """
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        return "Push endpoint must be an https URL."
    host = parsed.hostname
    if not host:
        return "Push endpoint has no host."
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return "Push endpoint host could not be resolved."
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return "Push endpoint must be a public address."
    return None


def send_push(subscription: dict, payload: dict) -> str:
    """Deliver one notification.

    Returns "sent", "gone" if the push service says this endpoint is dead
    and the caller should drop the row, or "failed" for anything else.

    The three states matter: the caller uses them to decide whether a
    reminder actually reached anyone, and a failure that's
    indistinguishable from success would let a reminder be marked as
    delivered when it wasn't.
    """
    reason = endpoint_rejection_reason(subscription.get("endpoint", ""))
    if reason:
        # Re-checked here, not just at subscribe time, so an endpoint whose
        # host has since started resolving somewhere internal isn't sent to.
        log.warning("Refusing push to unsafe endpoint: %s", reason)
        return "failed"

    v = _load_or_create_vapid()
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=v,
            vapid_claims={"sub": _VAPID_CLAIM_SUB},
            timeout=10,
        )
        return "sent"
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            # Endpoint retired by the push service - browser reinstalled,
            # site data cleared, subscription revoked.
            return "gone"
        log.warning("Push delivery failed (status=%s): %s", status, e)
        return "failed"
    except Exception as e:  # noqa: BLE001 - never let delivery break the sweep
        log.warning("Push delivery error: %s", e)
        return "failed"
