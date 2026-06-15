#!/usr/bin/env bash
set -e

/usr/sbin/sshd

cd /workspace

if [ ! -f manage.py ]; then
    echo "Creating Django project..."
    django-admin startproject config .
fi

python manage.py migrate

# Rakumo同期バッチ（毎時0分）- 停止中
# 再開するには以下のコメントを外してコンテナを再ビルドしてください
# mkdir -p /workspace/logs
# printenv | grep -E '^(DJANGO_SETTINGS_MODULE|GOOGLE_|DEBUG|SECRET_KEY|ALLOWED_HOSTS|DATABASE_URL)' > /etc/cron_env
# echo "0 * * * * root cd /workspace && env $(cat /etc/cron_env | xargs) python manage.py sync_from_rakumo >> /workspace/logs/rakumo_sync.log 2>&1" > /etc/cron.d/rakumo_sync
# chmod 0644 /etc/cron.d/rakumo_sync
# cron

exec python manage.py runserver 0.0.0.0:8000
