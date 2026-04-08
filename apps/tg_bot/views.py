"""
apps/tg_bot/views.py

Django webhook-view для Telegram Bot.
Telegram шлёт POST на /api/tg/webhook/<SECRET_TOKEN>/
SECRET_TOKEN — рандомная строка в .env (TG_WEBHOOK_SECRET), чтобы
посторонние не могли слать поддельные апдейты.
"""
import json
import logging

from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from aiogram.types import Update

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    async def post(self, request, token: str):
        import os
        from apps.tg_bot.bot import dp, TOKEN
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        # Проверяем секретный токен в URL
        expected = os.environ.get("TG_WEBHOOK_SECRET", "")
        if not expected or token != expected:
            logger.warning("Telegram webhook: неверный или отсутствующий токен")
            return HttpResponse(status=403)

        # Создаем новый Bot для текущего запроса (чтобы избежать "Event loop is closed" между запросами)
        local_bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

        try:
            data = json.loads(request.body)
            update = Update(**data)
            await dp.feed_update(bot=local_bot, update=update)
        except Exception as exc:
            logger.error("Ошибка обработки Telegram update: %s", exc, exc_info=True)
        finally:
            await local_bot.session.close()

        return HttpResponse("ok")
