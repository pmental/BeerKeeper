import csv
import io

from fastapi import HTTPException, UploadFile

_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Reads an upload in chunks, rejecting it as soon as it exceeds
    max_bytes rather than buffering an arbitrarily large file into memory
    first - a plain `await file.read()` has no size cap of its own, and
    neither FastAPI/Starlette nor uvicorn impose one by default."""
    chunks = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {max_bytes // (1024 * 1024)} MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def read_csv_upload(file: UploadFile, max_bytes: int) -> tuple[list[str], list[dict]]:
    """The header and rows of an uploaded CSV file.

    Parsed in full before anything is imported, so a file that turns out
    to be unreadable halfway through is refused as a whole with a reason
    the person can act on, rather than failing with a server error.
    """
    raw = await read_upload_limited(file, max_bytes)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail='That file isn\'t UTF-8 text. In Excel, save it as "CSV UTF-8" and try again.',
        )
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"Couldn't read that file as CSV: {e}")
    return list(reader.fieldnames or []), rows
