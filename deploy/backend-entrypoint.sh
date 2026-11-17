#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy

exec waitress-serve --listen=*:8000 --threads=8 config.wsgi:application

