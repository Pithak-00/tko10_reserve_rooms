#!/usr/bin/env bash
set -e

/usr/sbin/sshd

cd /workspace

if [ ! -f manage.py ]; then
    echo "Creating Django project..."
    django-admin startproject config .
fi

python manage.py migrate

exec python manage.py runserver 0.0.0.0:8000
