#!/bin/sh
set -e

python manage.py migrate --noinput

# Seed opcional (implementar o comando `seed` em core/management/commands/).
if [ "${SEED:-0}" = "1" ] && python manage.py help seed >/dev/null 2>&1; then
  python manage.py seed
fi

exec "$@"
