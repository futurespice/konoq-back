"""
run_bot_polling.py

Локальный запуск бота в polling-режиме для разработки и тестирования.
Webhook НЕ нужен — бот сам опрашивает Telegram серверы.

Запуск:
    source .venv/bin/activate
    python run_bot_polling.py

Остановка: Ctrl+C
"""
import asyncio
import os
import django

# Инициализируем Django до импорта моделей
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "konoq.settings")
django.setup()

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    from apps.tg_bot.bot import bot, dp, TOKEN, OWNER_ID

    if not TOKEN or TOKEN == "000:placeholder":
        logger.error("TG_BOT_TOKEN не задан в .env — бот не запустится.")
        return

    if not OWNER_ID:
        logger.warning("TG_OWNER_ID не задан — команды /stats и /finance доступны всем.")

    me = await bot.get_me()
    logger.info("Бот запущен: @%s (id=%d)", me.username, me.id)
    logger.info("Нажми Ctrl+C для остановки")

    # Удаляем webhook если был установлен (иначе polling не работает)
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
