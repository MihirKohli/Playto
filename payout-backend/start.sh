#!/bin/sh
set -e

python manage.py migrate
python manage.py seed

celery -A core worker -l info &
CELERY_PID=$!

exec python manage.py runserver 0.0.0.0:${PORT:-8000}
