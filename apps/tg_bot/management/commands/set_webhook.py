"""
apps/tg_bot/management/commands/set_webhook.py

Django management command для установки Telegram webhook.

Запуск на сервере:
    docker-compose exec web python manage.py set_webhook

Что делает:
  1. Берёт TG_BOT_TOKEN, TG_WEBHOOK_SECRET, SITE_URL из .env
  2. Регистрирует webhook URL в Telegram API
  3. Выводит статус

.env переменные:
  TG_BOT_TOKEN       — токен от @BotFather
  TG_WEBHOOK_SECRET  — секретный путь в URL (любая случайная строка)
  SITE_URL           — https://konoq-hostel.com
"""
import asyncio
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Регистрирует Telegram webhook для бота"

    def handle(self, *args, **options):
        asyncio.run(self._set_webhook())

    async def _set_webhook(self):
        token   = os.environ.get("TG_BOT_TOKEN", "")
        secret  = os.environ.get("TG_WEBHOOK_SECRET", "")
        site    = os.environ.get("SITE_URL", "").rstrip("/")

        if not token:
            self.stderr.write("❌ TG_BOT_TOKEN не задан в .env")
            return
        if not secret:
            self.stderr.write("❌ TG_WEBHOOK_SECRET не задан в .env")
            return
        if not site:
            self.stderr.write("❌ SITE_URL не задан в .env")
            return

        webhook_url = f"{site}/api/tg/webhook/{secret}/"
        self.stdout.write(f"Устанавливаю webhook: {webhook_url}")

        from apps.tg_bot.bot import bot
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )

        info = await bot.get_webhook_info()
        self.stdout.write(self.style.SUCCESS(
            f"✅ Webhook установлен!\n"
            f"   URL:              {info.url}\n"
            f"   Pending updates:  {info.pending_update_count}\n"
            f"   Last error:       {info.last_error_message or '—'}"
        ))

        await bot.session.close()
