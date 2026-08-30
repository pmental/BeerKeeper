import datetime as dt
import os
import secrets
import warnings

import bcrypt
from jose import jwt, JWTError

from app.database import DATA_DIR

_SECRET_KEY_FILE = os.path.join(DATA_DIR, ".secret_key")


def _load_or_create_secret_key() -> str:
    """Prefer CELLAR_SECRET_KEY. If it's not set, generate a random key and
    persist it to the data directory so it survives restarts (an
    unpersisted random key would silently log everyone out on every
    restart - not much better than a shared static one). This is a
    fallback for convenience, not the recommended path: still set
    CELLAR_SECRET_KEY explicitly in production, since losing the data
    directory also loses this generated key."""
    env_key = os.environ.get("CELLAR_SECRET_KEY", "").strip()
    if env_key:
        return env_key

    if os.path.exists(_SECRET_KEY_FILE):
        with open(_SECRET_KEY_FILE, "r", encoding="utf-8") as f:
            existing = f.read().strip()
        if existing:
            return existing

    warnings.warn(
        "CELLAR_SECRET_KEY is not set - generating a random key and saving it to "
        f"{_SECRET_KEY_FILE}. This works, but losing that file (e.g. a fresh volume) "
        "invalidates every existing login. Set CELLAR_SECRET_KEY explicitly for "
        "production use - see .env.example."
    )
    generated = secrets.token_hex(32)
    os.makedirs(os.path.dirname(_SECRET_KEY_FILE), exist_ok=True)
    with open(_SECRET_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(generated)
    return generated


SECRET_KEY = _load_or_create_secret_key()
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

# bcrypt only uses the first 72 bytes of input; longer passwords are truncated
# up front so hashing never raises on unusually long (but valid) passwords.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, username: str, issued_at: dt.datetime | None = None) -> str:
    # JWT NumericDate fields are whole seconds - truncate up front so a
    # token's real iat always exactly matches a cutoff set from the same
    # "now" (e.g. token_valid_after in a password-change/reset endpoint),
    # rather than risking the sub-second part getting lost only on one
    # side of that comparison and the token rejecting itself.
    now = (issued_at or dt.datetime.utcnow()).replace(microsecond=0)
    expire = now + dt.timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "username": username, "iat": now, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Returns the decoded payload (not just the user id) so callers can
    check claims like `iat` against server-side state, e.g. to honor a
    password change that should invalidate tokens issued before it."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
