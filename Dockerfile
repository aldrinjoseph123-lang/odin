# Odin — project lifecycle tracker
#
# Two stages: Node builds the React front end, then the Python runtime image
# (requirements.txt) gets only the built files. gunicorn serves the app; nginx
# in front of it terminates TLS and serves /static (see docker-compose.yml).
# Stage 1: the React front end. Only its build output crosses into the runtime
# image — Node never ships. Debian (glibc), not Alpine: v1.5.1's fresh npm ci
# on Alpine left rolldown (Vite's bundler) unable to load its native binary.
# Base images are pinned by version and digest, so every build starts from the
# same bytes (review P3-9). To take a newer one (security fixes in Debian),
# bump the tag and its digest together, and pin the multi-arch index digest (the
# one `docker buildx imagetools inspect` prints), not a single platform's image
# digest (Docker Hub's tags API lists those: the amd64 one comes first):
#   docker buildx imagetools inspect node:22.23.3-slim --format '{{.Manifest.Digest}}'
#   docker buildx imagetools inspect python:3.12.15-slim --format '{{.Manifest.Digest}}'
FROM node:22.23.3-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ODIN_DATA_DIR=/data \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so image layers cache on code changes. requirements.lock
# is requirements.txt with the sha256 of every file (scripts/make_lock.py): pip
# refuses anything else (and any package the lock leaves out), so a registry cannot hand this build different bytes.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .
COPY --from=frontend /frontend/dist ./frontend/dist

# Never run as root. /data is made here, owned by odin: Docker copies that
# ownership into the named volume the first time it is mounted. The
# entrypoint only checks the volume is writable (a bind mount or an older
# volume owned by someone else is refused with the fix); it never chowns.
RUN useradd --create-home --uid 10001 odin \
 && mkdir -p /data/uploads \
 && chown -R odin:odin /data   # code stays root-owned: the app cannot rewrite itself

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER odin
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
# The access line ends with the request id the app sets (X-Request-Id), so it
# can be matched with the app's log line and with the reference on an error page.
CMD ["gunicorn", "--preload", "--workers", "2", "--threads", "4", \
     "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", \
     "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\" %({x-request-id}o)s", \
     "--logger-class", "gunicorn_logger.RedactingLogger", "wsgi:app"]
