#!/bin/sh
set -e

echo "⏳ Ждём базу данных..."
until python -c "
import os, psycopg2
try:
    psycopg2.connect(
        dbname=os.environ.get('DB_NAME','konoq'),
        user=os.environ.get('DB_USER','konoq'),
        password=os.environ.get('DB_PASSWORD','konoq'),
        host=os.environ.get('DB_HOST','db'),
        port=os.environ.get('DB_PORT','5432'),
    )
    print('ok')
except Exception as e:
    raise SystemExit(1)
" 2>/dev/null; do
    echo "  ...база ещё не готова, повторяем через 2 сек"
    sleep 2
done
echo "✅ База готова"

echo "🔄 Применяем миграции..."
python manage.py migrate --noinput

echo "📦 Собираем статику..."
python manage.py collectstatic --noinput

echo "🌱 Засеваем номера (если ещё нет)..."
python manage.py seed_rooms

echo "🚀 Запускаем Gunicorn..."
exec gunicorn konoq.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
