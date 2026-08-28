import datetime as dt
import os

import bcrypt
from jose import jwt, JWTError

# In production, set CELLAR_SECRET_KEY to a long random value (see .env.example).
# A key is auto-generated on first boot if none is provided, but it will change
# on container recreation unless persisted, which would log everyone out.
SECRET_KEY = os.environ.get("CELLAR_SECRET_KEY") or "dev-insecure-secret-change-me"
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


def create_access_token(user_id: int, username: str) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
