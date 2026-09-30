#!/usr/bin/env bash
# Arranque en Render: migra la base (en el disco persistente) y levanta Gunicorn.
set -o errexit
python manage.py migrate --noinput

# Superusuario inicial sin Shell (útil en el plan free): definir DJANGO_SUPERUSER_EMAIL y
# DJANGO_SUPERUSER_PASSWORD. Si ya existe, no hace nada. Borrar las variables después.
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput 2>/dev/null || echo "Superusuario ya existente: sin cambios."
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 60 --access-logfile -
