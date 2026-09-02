import io
import os
import sqlite3
import tempfile
import zipfile

from app.database import DATA_DIR, DB_PATH

PENDING_RESTORE_PATH = os.path.join(DATA_DIR, ".pending_restore.zip")

ZIP_DB_ENTRY = "cellar.db"

# A backup/restore of a database that doesn't even loosely resemble this
# app's schema would be worse than useless - this is a cheap sanity check
# against uploading the wrong file, not full schema validation.
_EXPECTED_TABLES = {"users", "beers", "breweries", "cellar_entries", "consumption_logs"}


def create_backup_bytes() -> bytes:
    """A single zip with a consistent, point-in-time snapshot of the live
    database - every account, cellar, brewery, beer, and beer style, not
    just your own - using SQLite's own backup API, not just reading the
    file, which could catch it mid-write in this app's WAL mode."""
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(":memory:")
    try:
        source.backup(dest)
        db_bytes = dest.serialize()
    finally:
        source.close()
        dest.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ZIP_DB_ENTRY, db_bytes)
    return buf.getvalue()


def validate_backup_zip(data: bytes) -> None:
    """Raises ValueError with a human-readable reason if this doesn't look
    like a real, intact BeerKeeper backup. The database entry is validated
    via a real temp file rather than an in-memory connection: this app's
    databases are in WAL mode, and SQLite's `:memory:` databases handle a
    deserialized WAL-flagged header oddly (fails with "unable to open
    database file" even for a perfectly valid backup) - a real file
    sidesteps that entirely, and is a more faithful check anyway since a
    real file is exactly how this data gets used at actual restore time."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("That's not a valid backup file (not a zip archive).")

    if ZIP_DB_ENTRY not in zf.namelist():
        raise ValueError(f"That backup is missing {ZIP_DB_ENTRY} - doesn't look like a BeerKeeper backup.")

    db_bytes = zf.read(ZIP_DB_ENTRY)
    if not db_bytes.startswith(b"SQLite format 3\x00"):
        raise ValueError("The database inside that backup isn't a valid SQLite file.")

    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(db_bytes)
        conn = sqlite3.connect(tmp_path)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            if result[0] != "ok":
                raise ValueError(f"The database in that backup failed an integrity check: {result[0]}")
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
        except sqlite3.Error as e:
            raise ValueError(f"Couldn't read the database in that backup: {e}")
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
    validate_backup_zip(data)
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

    with open(PENDING_RESTORE_PATH, "rb") as f:
        data = f.read()
    zf = zipfile.ZipFile(io.BytesIO(data))

    # Remove any WAL/SHM companion files for the CURRENT db first - they
    # hold not-yet-checkpointed writes against the file being replaced,
    # and would either corrupt or be silently misapplied against the new
    # one otherwise.
    for suffix in ("-wal", "-shm"):
        stale = DB_PATH + suffix
        if os.path.exists(stale):
            os.remove(stale)

    # Write-to-temp-then-atomic-replace rather than writing directly over
    # the destination, so a process interrupted mid-write can't leave a
    # half-written database behind.
    tmp_db = DB_PATH + ".restoring"
    with open(tmp_db, "wb") as f:
        f.write(zf.read(ZIP_DB_ENTRY))
    os.replace(tmp_db, DB_PATH)

    os.remove(PENDING_RESTORE_PATH)
    return True
