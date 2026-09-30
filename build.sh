#!/usr/bin/env bash
# Build de Render. El disco persistente NO está disponible durante el build,
# por eso las migraciones se corren al arrancar (ver start.sh).
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
