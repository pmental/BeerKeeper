import os
import re
import warnings


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _ensure_scheme(raw: str, var_name: str) -> str:
    """A bare domain (no http:// or https://) is a common copy-paste mistake
    that used to crash deep inside authlib/httpx with a cryptic error at
    login time instead of failing clearly at startup. Auto-correct it (https
    is the right assumption for the vast majority of real providers) and
    say so loudly, so it's obvious what happened and how to override it."""
    raw = raw.strip().rstrip("/")
    if raw and not re.match(r"^https?://", raw, re.IGNORECASE):
        warnings.warn(
            f"{var_name}='{raw}' has no http:// or https:// scheme - assuming 'https://{raw}'. "
            f"Set it explicitly (e.g. https://{raw}, or http://{raw} for a plain-HTTP-only "
            f"instance) to avoid this warning."
        )
        raw = "https://" + raw
    return raw


PASSWORD_AUTH_ENABLED = _bool_env("CELLAR_PASSWORD_AUTH_ENABLED", True)

APP_NAME = "BeerKeeper"
# Bump this with every set of changes: 0.0.1, 0.0.2, ... until told to
# bump the minor/major version instead.
APP_VERSION = "0.0.55"

OIDC_ENABLED = _bool_env("CELLAR_OIDC_ENABLED", False)
OIDC_ISSUER = _ensure_scheme(os.environ.get("CELLAR_OIDC_ISSUER", ""), "CELLAR_OIDC_ISSUER")
OIDC_CLIENT_ID = os.environ.get("CELLAR_OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.environ.get("CELLAR_OIDC_CLIENT_SECRET", "").strip()
OIDC_SCOPES = os.environ.get("CELLAR_OIDC_SCOPES", "openid email profile").strip()
OIDC_BUTTON_LABEL = os.environ.get("CELLAR_OIDC_BUTTON_LABEL", "Continue with SSO").strip()
BASE_URL = _ensure_scheme(os.environ.get("CELLAR_BASE_URL", ""), "CELLAR_BASE_URL")

if OIDC_ENABLED and not (OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET and BASE_URL):
    warnings.warn(
        "CELLAR_OIDC_ENABLED is true but CELLAR_OIDC_ISSUER, CELLAR_OIDC_CLIENT_ID, "
        "CELLAR_OIDC_CLIENT_SECRET, and CELLAR_BASE_URL must all be set. "
        "Disabling OIDC until they are."
    )
    OIDC_ENABLED = False

if not PASSWORD_AUTH_ENABLED and not OIDC_ENABLED:
    warnings.warn(
        "CELLAR_PASSWORD_AUTH_ENABLED is false and OIDC is not configured/enabled - "
        "nobody will be able to log in. Enable one of them."
    )

# Comma/whitespace-separated usernames that should always be admins,
# re-applied on every boot. Mainly a recovery lever: if you ever end up
# with zero admins (shouldn't happen - see the auto-promotion logic in
# admin_bootstrap.py - but self-hosted things go sideways sometimes), set
# this and restart to get back in, rather than needing to edit the
# database by hand.
ADMIN_USERNAMES = [
    u.strip() for u in re.split(r"[,\s]+", os.environ.get("CELLAR_ADMIN_USERNAMES", "")) if u.strip()
]

# --- SMTP (password reset + welcome emails) ---------------------------
SMTP_HOST = os.environ.get("CELLAR_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("CELLAR_SMTP_PORT", "587").strip() or "587")
SMTP_USERNAME = os.environ.get("CELLAR_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("CELLAR_SMTP_PASSWORD", "")
# "starttls" (default, typically port 587): connect plain, then upgrade.
# "ssl": implicit TLS from the first byte (typically port 465).
# "none": no encryption at all - only for a trusted local relay.
SMTP_SECURITY = os.environ.get("CELLAR_SMTP_SECURITY", "starttls").strip().lower()
SMTP_FROM_EMAIL = os.environ.get("CELLAR_SMTP_FROM_EMAIL", "").strip()
SMTP_FROM_NAME = os.environ.get("CELLAR_SMTP_FROM_NAME", APP_NAME).strip()

SMTP_ENABLED = bool(SMTP_HOST and SMTP_FROM_EMAIL)

# For an internal relay using a self-signed cert. Off (secure, verified) by
# default; only turn this on if you know why you need to.
SMTP_SKIP_CERT_VERIFY = _bool_env("CELLAR_SMTP_SKIP_CERT_VERIFY", False)

if SMTP_ENABLED and SMTP_SECURITY not in ("starttls", "ssl", "none"):
    warnings.warn(
        f"CELLAR_SMTP_SECURITY='{SMTP_SECURITY}' is not one of starttls/ssl/none - assuming starttls."
    )
    SMTP_SECURITY = "starttls"

if SMTP_ENABLED and not BASE_URL:
    warnings.warn(
        "CELLAR_SMTP_HOST and CELLAR_SMTP_FROM_EMAIL are set but CELLAR_BASE_URL isn't - "
        "password reset links would be broken without it. Disabling email until it's set."
    )
    SMTP_ENABLED = False

