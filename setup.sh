#!/bin/bash
# Запускай из директории konoq-back:
# bash setup.sh

set -e  # остановить при любой ошибке

echo "📦 Устанавливаем зависимости..."
.venv/bin/pip install -r requirements.txt

echo "🗄️  Создаём миграции users..."
.venv/bin/python manage.py makemigrations users

echo "⚡ Применяем все миграции (включая simplejwt blacklist)..."
.venv/bin/python manage.py migrate

echo "👤 Создаём суперпользователя (admin / admin123)..."
.venv/bin/python manage.py shell -c "
from apps.users.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(
        username='admin',
        password='admin123',
        email='admin@konoq.kg',
        role='admin',
        first_name='Admin',
    )
    print('  ✅ admin / admin123')
else:
    print('  ℹ️  admin уже существует')
"

echo "👤 Создаём менеджера (manager / manager123)..."
.venv/bin/python manage.py shell -c "
from apps.users.models import User
if not User.objects.filter(username='manager').exists():
    User.objects.create_user(
        username='manager',
        password='manager123',
        email='manager@konoq.kg',
        role='manager',
        first_name='Менеджер',
    )
    print('  ✅ manager / manager123')
else:
    print('  ℹ️  manager уже существует')
"

echo ""
echo "✅ Готово! Запускай сервер:"
echo "   .venv/bin/python manage.py runserver"
echo ""
echo "📖 Документация:"
echo "   Swagger UI → http://127.0.0.1:8000/api/docs/"
echo "   ReDoc      → http://127.0.0.1:8000/api/redoc/"
echo "   Schema     → http://127.0.0.1:8000/api/schema/"
