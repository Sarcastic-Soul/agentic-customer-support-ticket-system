#!/bin/sh
# Runs before both the api and worker containers start their real command:
# create the extensions `make up` normally creates by hand, then apply
# migrations. Idempotent - safe for both containers to run it on every boot.
set -e

python <<'PY'
import psycopg
from app.config import settings

conn = psycopg.connect(settings.checkpoint_database_url, autocommit=True)
conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
conn.execute("CREATE EXTENSION IF NOT EXISTS citext")
conn.close()
PY

alembic upgrade head

exec "$@"
