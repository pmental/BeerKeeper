import os
import shutil

from app.database import DATA_DIR

_DEFAULT_STYLES_SOURCE = os.path.join(os.path.dirname(__file__), "beer_styles_default.txt")
STYLES_FILE = os.path.join(DATA_DIR, "beer_styles.txt")


def ensure_styles_file() -> None:
    """Seed the user-editable styles file from the bundled default exactly
    once. Never overwrites an existing file, so hand edits always survive
    upgrades/rebuilds - the file lives in CELLAR_DATA_DIR, not the image."""
    if not os.path.exists(STYLES_FILE):
        os.makedirs(os.path.dirname(STYLES_FILE), exist_ok=True)
        shutil.copyfile(_DEFAULT_STYLES_SOURCE, STYLES_FILE)


def get_beer_styles() -> list[str]:
    ensure_styles_file()
    styles: list[str] = []
    try:
        with open(STYLES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                styles.append(line)
    except OSError:
        return []

    # De-dupe (case-insensitive) while preserving the file's own order, in
    # case someone's hand edit introduces an accidental repeat.
    seen = set()
    out = []
    for s in styles:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out
