"""
apps/tg_bot/handlers/finance.py

Команда /finance — финансовая сводка за текущий или указанный месяц.

Использование:
  /finance            — текущий месяц
  /finance 2026 4     — апрель 2026
"""
import logging
from datetime import date
from decimal import Decimal
from asgiref.sync import sync_to_async

from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
from django.db.models.functions import ExtractDay

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from apps.bookings.models import Booking
from apps.finance.models import RevenueTarget

router = Router()
logger = logging.getLogger(__name__)

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март",    4: "Апрель",
    5: "Май",    6: "Июнь",    7: "Июль",     8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _get_finance_data(year: int, month: int) -> dict:
    """Собирает финансовые данные синхронно — вызываем через sync_to_async."""

    confirmed = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        checkin__year=year,
        checkin__month=month,
    ).select_related("branch")

    total_bookings = confirmed.count()

    # Считаем выручку: для каждого бронирования — nights × price_per_night номера.
    # Если price_is_per_bed=True, умножаем ещё на guests (места).
    # Так как у нас room — это CharField с типом (не FK на Room),
    # берём price_per_night из связанного Branch через room_type — пока считаем
    # через ручное суммирование по записям (масштабируется с FK позже).
    actual_revenue = Decimal("0")
    for b in confirmed:
        nights = b.nights
        if nights <= 0:
            continue
        # Базовая цена берётся из модели Room по branch + room_type
        # Пока: из seed_rooms — дормы 600 сом/место, двойные 1500/2000
        from apps.rooms.models import Room as RoomModel
        try:
            room_obj = RoomModel.objects.filter(
                branch=b.branch,
                room_type=b.room,
            ).first()
            if room_obj:
                if room_obj.price_is_per_bed:
                    price = room_obj.price_per_night * b.guests
                else:
                    price = room_obj.price_per_night
            else:
                price = Decimal("0")
        except Exception:
            price = Decimal("0")
        actual_revenue += price * nights

    # По каналам
    source_counts = {}
    for b in confirmed:
        src = b.get_source_display()
        source_counts[src] = source_counts.get(src, 0) + 1

    # По филиалам
    branch_counts = {}
    for b in confirmed:
        branch_name = b.branch.name if b.branch else "Не указан"
        branch_counts[branch_name] = branch_counts.get(branch_name, 0) + 1

    # План
    try:
        target_obj = RevenueTarget.objects.get(year=year, month=month)
        target = target_obj.target
    except RevenueTarget.DoesNotExist:
        target = None

    return {
        "total_bookings": total_bookings,
        "actual_revenue": actual_revenue,
        "target":         target,
        "by_source":      source_counts,
        "by_branch":      branch_counts,
    }


@router.message(Command("finance"))
async def cmd_finance(message: Message):
    today = date.today()
    parts = message.text.split()

    # Парсим опциональные год/месяц: /finance 2026 4
    try:
        year  = int(parts[1]) if len(parts) > 1 else today.year
        month = int(parts[2]) if len(parts) > 2 else today.month
        if not (1 <= month <= 12) or year < 2020:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("❌ Формат: /finance [год] [месяц]\nПример: /finance 2026 5")
        return

    data = await sync_to_async(_get_finance_data)(year, month)

    month_name = MONTHS_RU.get(month, str(month))
    actual = data["actual_revenue"]
    target = data["target"]

    # Процент выполнения плана
    if target and target > 0:
        pct = int(actual / target * 100)
        plan_line = f"📌 План:    <b>{target:,.0f} сом</b>\n✅ Факт:    <b>{actual:,.0f} сом</b>  ({pct}%)"
    else:
        plan_line = f"💰 Выручка: <b>{actual:,.0f} сом</b>\n📌 План не задан"

    text = (
        f"💼 <b>Финансы — {month_name} {year}</b>\n\n"
        f"🎫 Бронирований: <b>{data['total_bookings']}</b>\n"
        f"{plan_line}\n"
    )

    if data["by_branch"]:
        text += "\n<b>По филиалам:</b>\n"
        for branch_name, count in data["by_branch"].items():
            text += f"  🏢 {branch_name}: {count}\n"

    if data["by_source"]:
        text += "\n<b>По каналам:</b>\n"
        for src, count in data["by_source"].items():
            text += f"  📡 {src}: {count}\n"

    await message.answer(text)
