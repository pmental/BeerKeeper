FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first so they're cached separately from app code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
