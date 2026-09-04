import os
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import sessionmaker, declarative_base

from app import config

DATA_DIR = os.environ.get("CELLAR_DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "cellar.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    # SQLAlchemy's plain defaults (pool_size=5, max_overflow=10) are sized
    # for a real client-server database with many genuinely concurrent
    # connections. SQLite doesn't benefit the same way - writes serialize
    # to the single file regardless of how many connections exist - and
    # this app's realistic concurrency (a self-hosted personal/small-group
    # tool) is low. Keeping the same steady-state pool_size but dropping
    # max_overflow to 0 caps the worst case at 5 open connections instead
    # of 15, with no change to normal request handling.
    pool_size=5,
    max_overflow=0,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    # Foreign keys are off by default in SQLite; turn them on per-connection.
    # WAL mode lets reads proceed while a write is in flight, which matters
    # once more than one person is using the same self-hosted instance.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

    # SQLite's own LIKE/LOWER only case-fold ASCII a-z - "Örebro" stays
    # "Örebro" through LOWER(), never becomes "örebro". That silently
    # breaks case-insensitive search and duplicate-name checks for any
    # accented name (not just Swedish - German, French, Polish, etc. are
    # all affected), since ilike() relies on that same mechanism.
    # Registering a real Python-backed lower() - which *is*
    # Unicode-aware - and using it explicitly (see ilike_unicode() below)
    # fixes this without needing a SQLite build with the ICU extension,
    # which most platforms don't ship.
    dbapi_connection.create_function("unicode_lower", 1, lambda s: s.lower() if s is not None else None)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ilike_unicode(column, value):
    """A drop-in replacement for column.ilike(value) that also works
    correctly for non-ASCII names - see the unicode_lower() registration
    above for why plain ilike() can't be trusted here. Works the same way
    whether value has %-wildcards (a substring search) or is a plain
    string (an exact case-insensitive match, e.g. a duplicate-name
    check) - LIKE handles both once the case-folding itself is correct."""
    return func.unicode_lower(column).like(func.unicode_lower(value))


def run_migrations():
    """Lightweight additive migrations for SQLite: add any columns that
    exist in the ORM models but not yet in an existing database file.
    Safe to run on every startup; a fresh database has nothing to add."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return  # fresh install; create_all() will make the table with all columns

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "unit_system" not in existing_cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN unit_system VARCHAR(8) NOT NULL DEFAULT 'metric'")
            )
        if "oidc_subject" not in existing_cols:
            # A genuinely old install predating OIDC support entirely -
            # both columns are new here, so there's no existing data to
            # preserve or backfill.
            conn.execute(text("ALTER TABLE users ADD COLUMN oidc_subject VARCHAR(255)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN oidc_issuer VARCHAR(500)"))
            # SQLite treats each NULL as distinct for UNIQUE purposes, so a
            # composite unique index here still allows any number of
            # password-only users (both columns NULL) to coexist.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_oidc_issuer_subject "
                    "ON users (oidc_issuer, oidc_subject)"
                )
            )
        elif "oidc_issuer" not in existing_cols:
            # oidc_subject already exists and may already have real linked
            # accounts on it. OIDC's `sub` is only guaranteed unique
            # *within* a given issuer, so enforcing global uniqueness on
            # subject alone (the old index below) is a latent correctness
            # bug: if this instance ever switches OIDC providers, a new
            # provider's subject value could coincidentally collide with
            # an old, unrelated one already on file and link the wrong
            # account. Backfill the currently-configured issuer onto
            # already-linked accounts - correct for the overwhelming
            # majority of installs, which never change providers - then
            # replace the old single-column unique index with a composite
            # one on (issuer, subject) together.
            conn.execute(text("ALTER TABLE users ADD COLUMN oidc_issuer VARCHAR(500)"))
            if config.OIDC_ISSUER:
                conn.execute(
                    text(
                        "UPDATE users SET oidc_issuer = :issuer "
                        "WHERE oidc_subject IS NOT NULL AND oidc_issuer IS NULL"
                    ),
                    {"issuer": config.OIDC_ISSUER},
                )
            conn.execute(text("DROP INDEX IF EXISTS ix_users_oidc_subject"))
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_oidc_issuer_subject "
                    "ON users (oidc_issuer, oidc_subject)"
                )
            )
        if "display_name" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(255)"))

        if "token_valid_after" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN token_valid_after DATETIME"))

        if "avatar_url" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(1024)"))

        # Fix accounts stuck with an old OIDC placeholder email domain
        # (@oidc.invalid) that Pydantic's EmailStr rejects outright - left
        # in place, every response describing that account (starting with
        # /api/auth/me right after login) would 500 forever. See
        # oidc.py's _placeholder_email for the full story. Safe to run
        # every boot: a no-op once no matching rows are left.
        conn.execute(
            text(
                "UPDATE users SET email = REPLACE(email, '@oidc.invalid', '@no-reply.beerkeeper.internal') "
                "WHERE email LIKE '%@oidc.invalid'"
            )
        )

        if "instance_settings" in inspector.get_table_names():
            settings_cols = {c["name"] for c in inspector.get_columns("instance_settings")}
            smtp_columns = {
                "smtp_host": "VARCHAR(255)",
                "smtp_port": "INTEGER",
                "smtp_security": "VARCHAR(16)",
                "smtp_username": "VARCHAR(255)",
                "smtp_password": "VARCHAR(255)",
                "smtp_from_email": "VARCHAR(255)",
                "smtp_from_name": "VARCHAR(255)",
                "smtp_skip_cert_verify": "BOOLEAN",
            }
            for name, sql_type in smtp_columns.items():
                if name not in settings_cols:
                    conn.execute(text(f"ALTER TABLE instance_settings ADD COLUMN {name} {sql_type}"))

<<<<<<< HEAD
        # beers.brewery_id was missing an index despite being a foreign
        # key filtered on directly (the "does this beer already exist for
        # this brewery" check, on every beer creation and CSV import row)
        # - name matches what a fresh install's create_all() generates
        # for this column, so both paths converge on the same index.
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_beers_brewery_id ON beers (brewery_id)"))

=======
>>>>>>> 6f823f07956400636cd6feea940c2127861f5b3e

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
