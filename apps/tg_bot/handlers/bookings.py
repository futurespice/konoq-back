"""
apps/tg_bot/handlers/bookings.py

Команды и callback-кнопки для управления бронированиями.

Команды владельца:
  /start          — приветствие + список команд
  /bookings       — список ожидающих бронирований (pending)
  /booking <id>   — детали конкретного бронирования

Inline-кнопки (callback_data):
  confirm:<id>    — подтвердить бронирование
  cancel:<id>     — отменить бронирование
"""
import logging
from asgiref.sync import sync_to_async

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from apps.bookings.models import Booking

router = Router()
logger = logging.getLogger(__name__)


def _booking_text(b: Booking, detailed: bool = False) -> str:
    """Форматирует текст одного бронирования."""
    nights = b.nights
    night_word = "ночь" if nights == 1 else ("ночи" if 2 <= nights <= 4 else "ночей")

    text = (
        f"📋 <b>Бронирование #{b.id}</b>  |  {b.get_status_display()}\n\n"
        f"👤 {b.name} {b.surname}\n"
        f"📞 {b.phone}"
    )
    if b.email:
        text += f"\n✉️ {b.email}"
    text += (
        f"\n\n📅 <b>{b.checkin}</b> → <b>{b.checkout}</b> "
        f"({nights} {night_word})\n"
        f"🛏 {b.get_room_display()}  |  👥 {b.guests} чел.\n"
        f"🌍 {b.country}  ·  {b.get_purpose_display()}\n"
        f"📡 {b.get_source_display()}"
    )
    if b.branch:
        text += f"\n🏢 {b.branch.name}"
    if detailed and b.comment:
        text += f"\n\n💬 <i>{b.comment}</i>"
    return text


def _confirm_cancel_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{booking_id}"),
        InlineKeyboardButton(text="❌ Отменить",    callback_data=f"cancel:{booking_id}"),
    ]])


# ── /start ────────────────────────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 <b>KonoQ Hostel Bot</b>\n\n"
        "Доступные команды:\n"
        "/bookings — ожидающие бронирования\n"
        "/booking &lt;id&gt; — детали бронирования\n"
        "/stats — статистика сегодня\n"
        "/finance — выручка за текущий месяц"
    )


# ── /bookings ─────────────────────────────────────────────────────────────────
@router.message(Command("bookings"))
async def cmd_bookings(message: Message):
    bookings = await sync_to_async(list)(
        Booking.objects.select_related("branch")
        .filter(status=Booking.Status.PENDING)
        .order_by("-created_at")[:10]
    )

    if not bookings:
        await message.answer("✅ Нет ожидающих бронирований.")
        return

    await message.answer(f"⏳ <b>Ожидают подтверждения: {len(bookings)}</b>")

    for b in bookings:
        await message.answer(
            _booking_text(b),
            reply_markup=_confirm_cancel_kb(b.id),
        )


# ── /booking <id> ─────────────────────────────────────────────────────────────
@router.message(Command("booking"))
async def cmd_booking_detail(message: Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /booking &lt;id&gt;\nПример: /booking 42")
        return

    booking_id = int(parts[1])
    try:
        b = await sync_to_async(
            Booking.objects.select_related("branch").get
        )(pk=booking_id)
    except Booking.DoesNotExist:
        await message.answer(f"❌ Бронирование #{booking_id} не найдено.")
        return

    kb = None
    if b.status == Booking.Status.PENDING:
        kb = _confirm_cancel_kb(b.id)

    await message.answer(_booking_text(b, detailed=True), reply_markup=kb)


# ── Callback: confirm:<id> ────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("confirm:"))
async def cb_confirm(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])

    def _do_confirm():
        try:
            b = Booking.objects.get(pk=booking_id)
            if b.status != Booking.Status.CONFIRMED:
                b.status = Booking.Status.CONFIRMED
                b.save()
            return True
        except Booking.DoesNotExist:
            return False

    updated = await sync_to_async(_do_confirm)()

    if not updated:
        await callback.answer("❌ Бронирование не найдено.", show_alert=True)
        return

    await callback.answer("✅ Подтверждено!")
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>ПОДТВЕРЖДЕНО</b>",
        reply_markup=None,
    )


# ── Callback: cancel:<id> ─────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery):
    booking_id = int(callback.data.split(":")[1])

    def _do_cancel():
        try:
            b = Booking.objects.get(pk=booking_id)
            if b.status != Booking.Status.CANCELLED:
                b.status = Booking.Status.CANCELLED
                b.save()
            return True
        except Booking.DoesNotExist:
            return False

    updated = await sync_to_async(_do_cancel)()

    if not updated:
        await callback.answer("❌ Бронирование не найдено.", show_alert=True)
        return

    await callback.answer("🚫 Отменено.")
    await callback.message.edit_text(
        callback.message.text + "\n\n🚫 <b>ОТМЕНЕНО</b>",
        reply_markup=None,
    )
