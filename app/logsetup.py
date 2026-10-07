"""Log level for the whole app, from CELLAR_LOG_LEVEL.

Imported first by app.main, so the level is in place before anything
else gets a chance to log.
"""
import logging
import os

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}
_DEFAULT = "info"


class _PrefixFormatter(logging.Formatter):
    """The same "LEVEL:    message" shape as uvicorn's own lines."""

    def format(self, record: logging.LogRecord) -> str:
        record.levelprefix = f"{record.levelname + ':':<9}"
        # Captured Python warnings arrive with a trailing newline.
        return super().format(record).rstrip("\n")


def _configure() -> None:
    raw = (os.environ.get("CELLAR_LOG_LEVEL") or "").strip().lower()
    level = _LEVELS.get(raw, _LEVELS[_DEFAULT])

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_PrefixFormatter("%(levelprefix)s %(message)s"))
        root.addHandler(handler)

    # This app's own loggers follow the setting exactly. Libraries are
    # never louder than warnings, however low the setting goes: their
    # debug output is noise here and isn't written with our logs in mind.
    logging.getLogger("cellar").setLevel(level)
    root.setLevel(max(level, logging.WARNING))
    # Python warnings (deprecations, config notices) become ordinary
    # WARNING lines, so "error" silences them like any other warning.
    logging.captureWarnings(True)

    if raw in _LEVELS:
        # uvicorn has configured these by the time the app is imported.
        # Left alone when the variable is unset, so a --log-level given on
        # the command line still applies.
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logging.getLogger(name).setLevel(level)
    elif raw:
        logging.getLogger("cellar.config").warning(
            "CELLAR_LOG_LEVEL is not a valid level (%r); using %s. "
            "Choose from debug, info, warning, error or critical.",
            raw,
            _DEFAULT,
        )


_configure()
