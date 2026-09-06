# Floating minor-version tag, not a pinned patch+codename - most of the
# CVEs a scanner flags in this image are Debian/glibc-level OS package
# issues, not the Python interpreter itself, and get fixed by the official
# image maintainers' periodic rebuilds. Pinning to an exact patch version
# would freeze this at whatever OS security patch level existed on the day
# it was built, working against that. Rebuild with --pull to pick up fixes.
FROM python:3.14-slim

WORKDIR /app

# Install Python dependencies first so they're cached separately from app code.
# Installs from the lock file (the exact, fully-pinned transitive tree),
# not requirements.txt directly - see requirements-lock.txt's own header
# for why. requirements.txt is still what to edit when adding/upgrading a
# direct dependency; regenerate the lock file afterward.
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY app ./app
COPY static ./static

RUN useradd --create-home --uid 1000 cellar \
    && mkdir -p /data \
    && chown -R cellar:cellar /app /data
USER cellar

ENV CELLAR_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
