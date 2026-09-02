import os

from sqlalchemy.orm import Session

from app import models
from app.database import DATA_DIR

_DEFAULT_STYLES_SOURCE = os.path.join(os.path.dirname(__file__), "beer_styles_default.txt")

# Styles used to live here as a hand-editable plain text file, outside the
# database entirely - which meant a database-only backup would silently
# drop any custom styles, and backup.py had to bundle this file in
# separately to work around it. Kept only as a one-time migration source
# below; nothing reads or writes it anymore once that's run.
_LEGACY_STYLES_FILE = os.path.join(DATA_DIR, "beer_styles.txt")


def _parse_styles_file(path: str) -> list[str]:
    styles = []
    seen = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            styles.append(line)
    return styles


def migrate_beer_styles_if_needed(db: Session) -> None:
    """One-time move from the old beer_styles.txt file into the database.
    Runs at every startup but only actually does anything once: if the
    beer_styles table already has rows - whether from a previous run of
    this migration, or because someone's since added styles through the
    admin panel - it's a no-op, so this is always safe to call.

    Prefers an existing beer_styles.txt if this install has one (so any
    hand edits survive the move exactly as they were), falling back to
    the bundled default list for an install that never had one."""
    if db.query(models.BeerStyle).first():
        return

    source = _LEGACY_STYLES_FILE if os.path.exists(_LEGACY_STYLES_FILE) else _DEFAULT_STYLES_SOURCE
    if not os.path.exists(source):
        return

    for i, name in enumerate(_parse_styles_file(source)):
        db.add(models.BeerStyle(name=name, sort_order=i))
    db.commit()
