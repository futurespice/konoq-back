"""
apps/tg_bot/bot.py

Инициализация Bot и Dispatcher (aiogram 3.x).
Бот запускается через Django webhook-view, не через polling.

Переменные окружения (в .env):
  TG_BOT_TOKEN   — токен бота от @BotFather
  TG_OWNER_ID    — Telegram user_id владельца (Эрнис)
"""
import os
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)

# ── Инициализация ─────────────────────────────────────────────────────────────
TOKEN    = os.environ.get("TG_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("TG_OWNER_ID", "0"))

if not TOKEN:
    logger.warning("TG_BOT_TOKEN не задан — Telegram Bot отключён.")

bot = Bot(
    token=TOKEN or "000:placeholder",
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

# ── Регистрация роутеров (импортируем после создания dp) ──────────────────────
from apps.tg_bot.handlers import bookings as bookings_handler  # noqa: E402
from apps.tg_bot.handlers import stats    as stats_handler     # noqa: E402
from apps.tg_bot.handlers import finance  as finance_handler   # noqa: E402

dp.include_router(bookings_handler.router)
dp.include_router(stats_handler.router)
dp.include_router(finance_handler.router)


# ── Утилита для отправки уведомлений ─────────────────────────────────────────
async def notify_owner(text: str) -> None:
    """Отправляет сообщение владельцу (Эрнису). Тихо проглатывает ошибки."""
    if not TOKEN or not OWNER_ID:
        return
    
    bot_instance = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot_instance.send_message(OWNER_ID, text)
    except Exception as exc:
        logger.error("Ошибка отправки уведомления в Telegram: %s", exc)
    finally:
        await bot_instance.session.close()


async def notify_owner_new_booking(booking) -> None:
    """Уведомление о новом бронировании с кнопками Подтвердить / Отменить."""
    if not TOKEN or not OWNER_ID:
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    text = (
        f"🏠 <b>Новое бронирование #{booking.id}</b>\n\n"
        f"👤 {booking.name} {booking.surname}\n"
        f"📞 {booking.phone}\n"
        f"📅 {booking.checkin} → {booking.checkout} "
        f"({booking.nights} {'ночь' if booking.nights == 1 else 'ночей'})\n"
        f"🛏 {booking.get_room_display()}\n"
        f"👥 Гостей: {booking.guests}\n"
        f"🌍 {booking.country} · {booking.get_purpose_display()}\n"
        f"📡 {booking.get_source_display()}"
    )
    if booking.branch:
        text += f"\n🏢 {booking.branch.name}"
    if booking.comment:
        text += f"\n💬 {booking.comment}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{booking.id}"),
        InlineKeyboardButton(text="❌ Отменить",    callback_data=f"cancel:{booking.id}"),
    ]])

    bot_instance = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot_instance.send_message(OWNER_ID, text, reply_markup=kb)
    except Exception as exc:
        logger.error("Ошибка отправки уведомления о бронировании: %s", exc)
    finally:
        await bot_instance.session.close()
