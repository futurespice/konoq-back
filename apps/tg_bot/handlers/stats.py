"""
apps/tg_bot/handlers/stats.py

Команда /stats — статистика бронирований за сегодня и текущий месяц.
"""
import logging
from datetime import date
from asgiref.sync import sync_to_async

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from apps.bookings.models import Booking

router = Router()
logger = logging.getLogger(__name__)


def _count(qs):
    return qs.count()


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    today = date.today()

    # Сегодняшние заезды
    arriving_today = await sync_to_async(_count)(
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin=today,
        )
    )
    # Сегодняшние выезды
    departing_today = await sync_to_async(_count)(
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkout=today,
        )
    )
    # Текущие гости (заехали, ещё не выехали)
    current_guests = await sync_to_async(_count)(
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin__lte=today,
            checkout__gt=today,
        )
    )
    # Ожидают подтверждения
    pending = await sync_to_async(_count)(
        Booking.objects.filter(status=Booking.Status.PENDING)
    )
    # За текущий месяц
    month_confirmed = await sync_to_async(_count)(
        Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin__year=today.year,
            checkin__month=today.month,
        )
    )

    await message.answer(
        f"📊 <b>Статистика KonoQ</b>\n"
        f"📅 {today.strftime('%d.%m.%Y')}\n\n"
        f"🛎 Заезд сегодня:   <b>{arriving_today}</b>\n"
        f"🚪 Выезд сегодня:   <b>{departing_today}</b>\n"
        f"🏠 Гостей сейчас:   <b>{current_guests}</b>\n"
        f"⏳ Ожидают подтв.:  <b>{pending}</b>\n\n"
        f"📆 Подтв. за месяц: <b>{month_confirmed}</b>"
    )
