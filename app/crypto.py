"""Symmetric encryption for secrets stored at rest in the database -
currently just the SMTP password. Not for user passwords, which are
hashed (one-way, never need to be read back), not encrypted.

Uses a key derived from the app's own CELLAR_SECRET_KEY via SHA-256, so
there's no separate secret to generate, store, or lose track of.

What this protects against: someone getting hold of just the database
file, or a backup of it, without also having the app's secret key - a
leaked backup, a misplaced disk, a copy of cellar.db shared by mistake.
In those cases the stored value is ciphertext, not a readable password.

What this does NOT protect against: a fully compromised running server.
The key lives right next to the encrypted data there too (same env,
same filesystem), so anyone with that level of access has both already.
That's an inherent limit of deriving the key from a secret this app
already manages itself, rather than an external secrets vault or HSM -
correct for this app's scale, but worth being honest about.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.auth import SECRET_KEY


def _fernet() -> Fernet:
    # Fernet requires a 32-byte, url-safe base64-encoded key; SHA-256
    # deterministically gives 32 bytes from a secret of any length.
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """Raises InvalidToken if value isn't valid ciphertext for this key -
    callers that might see a pre-migration plaintext value (see
    email.py's encrypt_existing_smtp_password_if_needed) should catch
    this explicitly rather than let it propagate."""
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


__all__ = ["encrypt_secret", "decrypt_secret", "InvalidToken"]
