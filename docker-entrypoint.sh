#!/bin/sh
# Fail fast on the two things that silently break a production deploy:
# a missing signing key, and a data directory the app cannot write to.
set -e

if [ -z "$SECRET_KEY" ]; then
  echo "FATAL: SECRET_KEY is not set. Generate one with:" >&2
  echo "  python3 -c 'import secrets; print(secrets.token_hex(32))'" >&2
  exit 1
fi

if [ ! -w "${ODIN_DATA_DIR:-/data}" ]; then
  echo "FATAL: ${ODIN_DATA_DIR:-/data} is not writable by uid $(id -u)." >&2
  echo "Check the volume's ownership on the host." >&2
  exit 1
fi

exec "$@"
