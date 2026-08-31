def sanitize_url(raw: str | None, max_len: int = 500) -> str | None:
    """Only accept something that's plausibly a real, safe link. This ends
    up rendered straight into an href - unlike an <img src>, a scheme
    like javascript: in an <a href> actually executes when clicked, so
    this is a real (if narrow) stored-XSS vector if left unvalidated,
    not just a cosmetic broken-link concern."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")) or len(raw) > max_len:
        return None
    return raw
