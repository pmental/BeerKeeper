import datetime as dt
import os
import secrets
import warnings

import bcrypt
import jwt

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
TOKEN_EXPIRE_DAYS = 14

# bcrypt only uses the first 72 bytes of input. Every password-setting
# endpoint already enforces this at the schema level (see PasswordStr in
# schemas.py), so a call here with something longer means that guard was
# skipped somewhere - surface it loudly rather than silently truncate,
# which risks two different long passwords quietly hashing to the same
# value.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password is {len(encoded)} bytes, over bcrypt's {_MAX_PASSWORD_BYTES}-byte limit - "
            "this should have been rejected before reaching hash_password()."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        # No stored hash could ever have been created from something this
        # long (hash_password() above refuses it), so this can never be a
        # correct password - a wrong-length guess, not an error.
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, username: str, issued_at: dt.datetime | None = None) -> str:
    # JWT NumericDate fields are whole seconds - truncate up front so a
    # token's real iat always exactly matches a cutoff set from the same
    # "now" (e.g. token_valid_after in a password-change/reset endpoint),
    # rather than risking the sub-second part getting lost only on one
    # side of that comparison and the token rejecting itself.
    now = (issued_at or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0)
    expire = now + dt.timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "username": username, "iat": now, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Returns the decoded payload (not just the user id) so callers can
    check claims like `iat` against server-side state, e.g. to honor a
    password change that should invalidate tokens issued before it."""
    try:
        # Every token this app issues always has exp and iat (see
        # create_access_token above) - requiring them explicitly rather
        # than relying on PyJWT's own defaults means a future library
        # change or misconfiguration can't silently accept a token
        # missing either.
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat"]},
        )
    except jwt.PyJWTError:
        return None
