import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DATA_DIR = os.environ.get("CELLAR_DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "cellar.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
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


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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
            conn.execute(text("ALTER TABLE users ADD COLUMN oidc_subject VARCHAR(255)"))
            # SQLite treats each NULL as distinct for UNIQUE purposes, so a plain
            # unique index here still allows any number of password-only users
            # (oidc_subject IS NULL) to coexist.
            conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_oidc_subject ON users (oidc_subject)")
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
