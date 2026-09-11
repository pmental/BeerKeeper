import os

from sqlalchemy import func
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

# Which style names this install has already tried to seed. Mirrors the
# brewery seeder's marker file, and exists for the same reason: without
# it, adding a style to the bundled list would only ever reach brand-new
# installs, and re-adding on every boot would resurrect styles you'd
# deliberately deleted.
_SEEDED_NAMES_FILE = os.path.join(DATA_DIR, ".beer_styles_seeded_names")


def _load_seeded_names() -> set[str]:
    if not os.path.exists(_SEEDED_NAMES_FILE):
        return set()
    with open(_SEEDED_NAMES_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _record_seeded_names(keys) -> None:
    os.makedirs(os.path.dirname(_SEEDED_NAMES_FILE), exist_ok=True)
    with open(_SEEDED_NAMES_FILE, "a", encoding="utf-8") as f:
        for key in keys:
            f.write(key + "\n")


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


def seed_beer_styles_if_needed(db: Session) -> None:
    """Add any styles from beer_styles_default.txt that this install
    hasn't tried to seed before, so a later release adding styles reaches
    existing installs and not just fresh ones. Each name is recorded once
    attempted, which is what stops a style you've deliberately deleted
    from being silently recreated on the next boot.

    On the very first run after upgrading to a version with this, there's
    no marker file yet, so the styles currently in the table are recorded
    as already-attempted before anything is added. That keeps this from
    resurrecting the whole default list on an install that has pruned it.
    The one thing it can't tell apart is a default style you deleted
    before upgrading versus one that's genuinely new in the bundled list -
    the former will come back once, and stay gone after you delete it
    again. (Same caveat, and the same cause, as the brewery seeder's.)
    """
    if not os.path.exists(_DEFAULT_STYLES_SOURCE):
        return

    existing = {name.lower() for (name,) in db.query(models.BeerStyle.name).all()}

    first_run = not os.path.exists(_SEEDED_NAMES_FILE)
    if first_run:
        if not existing:
            # Nothing seeded yet at all - migrate_beer_styles_if_needed()
            # handles the initial fill, including the legacy-file case.
            # Recording its result here means the next boot doesn't treat
            # those styles as new.
            return
        _record_seeded_names(sorted(existing))

    already_attempted = _load_seeded_names()

    # Appended after everything already in the table rather than slotted
    # into the bundled file's position, matching what the admin panel's
    # own "add style" does (max + 1). A style added later therefore sorts
    # to the end of the dropdown rather than next to its neighbours in
    # the bundled file - renumbering to match the file would fix that,
    # but at the cost of rewriting sort_order on rows this run didn't
    # touch. Ordering only affects the order the picker lists styles in,
    # and it's filtered by typing anyway.
    next_order = db.query(func.max(models.BeerStyle.sort_order)).scalar()
    next_order = 0 if next_order is None else next_order + 1

    newly_attempted = []
    for name in _parse_styles_file(_DEFAULT_STYLES_SOURCE):
        key = name.lower()
        if key in already_attempted:
            continue
        newly_attempted.append(key)
        if key not in existing:
            db.add(models.BeerStyle(name=name, sort_order=next_order))
            existing.add(key)
            next_order += 1

    if not newly_attempted:
        return

    db.commit()
    _record_seeded_names(newly_attempted)
