# Odin — project lifecycle tracker
#
# Runtime image only: there is no build step (no npm, no bundler), so this is
# just Python + the three runtime dependencies. gunicorn serves the app; nginx
# in front of it terminates TLS and serves /static (see docker-compose.yml).
# Stage 1: the React front end. Only its build output crosses into the runtime
# image — Node never ships.
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so image layers cache on code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /frontend/dist ./frontend/dist

# Never run as root. The data directory is a mounted volume, so it is chowned
# at container start by the entrypoint rather than baked in here.
RUN useradd --create-home --uid 10001 odin \
 && mkdir -p /data/uploads \
 && chown -R odin:odin /app /data

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER odin
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "--preload", "--workers", "2", "--threads", "4", \
     "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
