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
