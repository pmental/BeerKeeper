import os
import sqlite3
import tempfile

from app.database import DATA_DIR, DB_PATH

PENDING_RESTORE_PATH = os.path.join(DATA_DIR, ".pending_restore.db")

# A backup/restore of a database that doesn't even loosely resemble this
# app's schema would be worse than useless - this is a cheap sanity check
# against uploading the wrong file, not full schema validation.
_EXPECTED_TABLES = {"users", "beers", "breweries", "cellar_entries", "consumption_logs"}


def create_backup_bytes() -> bytes:
    """A consistent, point-in-time snapshot of the live database using
    SQLite's own backup API - not just reading the file, which (especially
    in WAL mode, where this app runs) could catch it mid-write. Serialized
    to raw bytes in the same format as the real on-disk file, so it can be
    handed straight back as a download and later written back out unchanged."""
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(":memory:")
    try:
        source.backup(dest)
        return dest.serialize()
    finally:
        source.close()
        dest.close()


def validate_backup_bytes(data: bytes) -> None:
    """Raises ValueError with a human-readable reason if this doesn't look
    like a real, intact BeerKeeper database. Validated via a real temp
    file rather than an in-memory connection: this app's databases are in
    WAL mode, and SQLite's `:memory:` databases handle a deserialized
    WAL-flagged header oddly (fails with "unable to open database file"
    even for a perfectly valid backup) - a real file sidesteps that
    entirely, and is a more faithful check anyway since a real file is
    exactly how this data gets used at actual restore time."""
    if not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("That's not a SQLite database file.")

    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        conn = sqlite3.connect(tmp_path)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            if result[0] != "ok":
                raise ValueError(f"That database file failed an integrity check: {result[0]}")
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
        except sqlite3.Error as e:
            raise ValueError(f"Couldn't read that as a SQLite database: {e}")
        finally:
            conn.close()
    finally:
        os.remove(tmp_path)

    missing = _EXPECTED_TABLES - tables
    if missing:
        raise ValueError(f"Doesn't look like a BeerKeeper database (missing tables: {', '.join(sorted(missing))}).")


def stage_restore(data: bytes) -> None:
    """Validates and stages a restore for the *next startup* - deliberately
    not applied to the live database. Swapping a SQLite file out from
    under an active connection pool is exactly the kind of thing that
    corrupts data; doing the swap at a clean startup, before any
    connection is opened, is the safe way to do this."""
    validate_backup_bytes(data)
    with open(PENDING_RESTORE_PATH, "wb") as f:
        f.write(data)


def cancel_pending_restore() -> bool:
    if os.path.exists(PENDING_RESTORE_PATH):
        os.remove(PENDING_RESTORE_PATH)
        return True
    return False


def has_pending_restore() -> bool:
    return os.path.exists(PENDING_RESTORE_PATH)


def apply_pending_restore_if_any() -> bool:
    """Called at startup, before any DB connection is opened anywhere else
    in the app. Returns True if a restore was applied."""
    if not os.path.exists(PENDING_RESTORE_PATH):
        return False

    # Remove any WAL/SHM companion files for the CURRENT db first - they
    # hold not-yet-checkpointed writes against the file being replaced,
    # and would either corrupt or be silently misapplied against the new
    # one otherwise.
    for suffix in ("-wal", "-shm"):
        stale = DB_PATH + suffix
        if os.path.exists(stale):
            os.remove(stale)

    os.replace(PENDING_RESTORE_PATH, DB_PATH)
    return True
