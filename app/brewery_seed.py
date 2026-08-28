import os

from sqlalchemy.orm import Session

from app import models
from app.database import DATA_DIR

_DEFAULT_SOURCE = os.path.join(os.path.dirname(__file__), "breweries_default.txt")
_SEEDED_NAMES_FILE = os.path.join(DATA_DIR, ".breweries_seeded_names")


def _parse_line(raw: str):
    line = raw.strip()
    if not line or line.startswith("#"):
        return None
    if "|" in line:
        name, website = line.split("|", 1)
        name = name.strip()
        website = website.strip() or None
    else:
        name, website = line, None
    return (name, website) if name else None


def _load_seeded_names() -> set[str]:
    if not os.path.exists(_SEEDED_NAMES_FILE):
        return set()
    with open(_SEEDED_NAMES_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def seed_breweries_if_needed(db: Session) -> None:
    """Add any breweries from breweries_default.txt that haven't been
    individually seeded before. Each brewery name is tracked once it's
    been attempted (successfully created or already present), recorded in
    _SEEDED_NAMES_FILE - so later app updates that add more entries to the
    default list reach existing installs too, while a brewery you've
    deliberately deleted after it was seeded is never silently recreated.
    (Versions before 0.0.5 used a single all-or-nothing marker instead;
    upgrading from one of those treats nothing as previously attempted,
    so if you'd deleted one of that version's seeded breweries before
    upgrading, it may reappear once - sorry. Anything seeded from 0.0.5
    onward won't have that problem.)
    """
    if not os.path.exists(_DEFAULT_SOURCE):
        return

    already_attempted = _load_seeded_names()
    seen_this_run = set()
    newly_attempted = []

    with open(_DEFAULT_SOURCE, "r", encoding="utf-8") as f:
        for raw in f:
            parsed = _parse_line(raw)
            if not parsed:
                continue
            name, website = parsed
            key = name.lower()
            if key in already_attempted or key in seen_this_run:
                continue
            seen_this_run.add(key)
            newly_attempted.append(key)
            if not db.query(models.Brewery).filter(models.Brewery.name.ilike(name)).first():
                db.add(models.Brewery(name=name, website=website))

    if not newly_attempted:
        return

    db.commit()
    os.makedirs(os.path.dirname(_SEEDED_NAMES_FILE), exist_ok=True)
    with open(_SEEDED_NAMES_FILE, "a", encoding="utf-8") as f:
        for key in newly_attempted:
            f.write(key + "\n")

