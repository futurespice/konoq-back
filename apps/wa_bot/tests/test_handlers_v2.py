"""
apps/wa_bot/tests/test_handlers_v2.py

Тесты нового диалога WhatsApp-бота (Этап 3a, часть B): автоподбор шконок,
приватность, fallback, перехват гонки на шаге ввода имени.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.bookings.models import Booking, BookingBed
from apps.bookings.services import create_booking_with_beds
from apps.rooms.models import Bed, Branch, Room
from apps.wa_bot.handlers import handle_message
from apps.wa_bot.models import WhatsAppSession


def _make_room(branch, number, room_type, capacity, price, *, per_bed=True):
    room = Room.objects.create(
        branch=branch, number=number, room_type=room_type,
        capacity=capacity, price_per_night=price, price_is_per_bed=per_bed,
    )
    for i in range(1, capacity + 1):
        Bed.objects.create(room=room, label=str(i))
    return room


class WaHandlerV2Tests(TestCase):
    """Сценарии happy-path и fallback для WhatsApp-бота v2."""

    def setUp(self):
        self.branch = Branch.objects.create(name="WA V2 Branch")
        self.phone = "996700000000"
        self.contact_id = "contact-test"
        self.checkin = date.today() + timedelta(days=10)
        self.checkout = self.checkin + timedelta(days=2)

    def _walk_to_private_step(self, guests: int):
        """Прогнать диалог до шага приватности (после ввода гостей)."""
        handle_message(self.phone, "hi", self.contact_id)       # → await_lang
        handle_message(self.phone, "1", self.contact_id)        # RU → await_dates
        handle_message(self.phone,
                       f"{self.checkin.strftime('%d.%m.%Y')} "
                       f"{self.checkout.strftime('%d.%m.%Y')}",
                       self.contact_id)                          # → await_guests
        handle_message(self.phone, str(guests), self.contact_id)

    @patch("apps.wa_bot.handlers.send_wa_message")
    @patch("apps.bookings.services.notify_new_booking")
    def test_full_happy_path_dorm(self, mock_notify, mock_send):
        _make_room(self.branch, "D1", Room.RoomType.DORM_4, 4, 500)

        self._walk_to_private_step(4)                            # → await_private
        handle_message(self.phone, "2", self.contact_id)         # not private → await_room
        handle_message(self.phone, "1", self.contact_id)         # pick dorm_4 → await_bed
        handle_message(self.phone, "1", self.contact_id)         # confirm → await_name
        handle_message(self.phone, "Azat Test", self.contact_id)  # name → book

        self.assertEqual(Booking.objects.count(), 1)
        b = Booking.objects.first()
        self.assertEqual(b.beds.count(), 4)
        self.assertEqual(b.room, "")          # v2 путь не заполняет legacy поле
        self.assertFalse(b.is_private_booking)

        session = WhatsAppSession.objects.get(phone=self.phone)
        self.assertEqual(session.state, WhatsAppSession.State.START)

    @patch("apps.wa_bot.handlers.send_wa_message")
    @patch("apps.bookings.services.notify_new_booking")
    def test_private_booking_flow(self, mock_notify, mock_send):
        _make_room(self.branch, "D1", Room.RoomType.DORM_4, 4, 500)

        self._walk_to_private_step(4)
        handle_message(self.phone, "1", self.contact_id)         # private=True
        handle_message(self.phone, "1", self.contact_id)         # pick dorm_4
        handle_message(self.phone, "1", self.contact_id)         # confirm
        handle_message(self.phone, "Azat Test", self.contact_id)

        b = Booking.objects.get()
        self.assertEqual(b.beds.count(), 4)
        self.assertTrue(b.is_private_booking)

    @patch("apps.wa_bot.handlers.send_wa_message")
    @patch("apps.bookings.services.notify_new_booking")
    def test_private_fails_fallback_to_auto_assign(self, mock_notify, mock_send):
        room = _make_room(self.branch, "D1", Room.RoomType.DORM_4, 4, 500)
        # Занять 1 шконку, чтобы "комната целиком" была недоступна,
        # но 3 шконки оставались для обычного подбора
        create_booking_with_beds(
            branch_id=self.branch.id,
            beds=[room.beds.order_by("label").first()],
            checkin=self.checkin,
            checkout=self.checkout,
            name="Other", phone="+996777777777",
            country="KG", purpose=Booking.Purpose.OTHER,
        )
        existing_beds = BookingBed.objects.count()

        self._walk_to_private_step(3)
        handle_message(self.phone, "1", self.contact_id)         # private=True
        handle_message(self.phone, "1", self.contact_id)         # pick dorm_4 → fallback preview
        # Убедимся что в preview показан fallback (видно по is_fallback во флаге)
        session = WhatsAppSession.objects.get(phone=self.phone)
        self.assertEqual(session.state, WhatsAppSession.State.AWAIT_BED_CONFIRM)
        self.assertTrue(session.data.get("is_fallback"))

        handle_message(self.phone, "1", self.contact_id)         # confirm fallback
        handle_message(self.phone, "Azat Test", self.contact_id)

        # У предыдущей брони 1 шконка + новая 3 → итого 4
        self.assertEqual(BookingBed.objects.count(), existing_beds + 3)
        new_booking = Booking.objects.latest("created_at")
        self.assertEqual(new_booking.beds.count(), 3)
        self.assertFalse(new_booking.is_private_booking)

    @patch("apps.wa_bot.handlers.send_wa_message")
    @patch("apps.bookings.services.notify_new_booking")
    def test_bed_reservation_between_preview_and_confirm(self, mock_notify, mock_send):
        room = _make_room(self.branch, "D1", Room.RoomType.DORM_2, 2, 500)

        self._walk_to_private_step(2)
        handle_message(self.phone, "2", self.contact_id)         # not private
        handle_message(self.phone, "1", self.contact_id)         # pick dorm_2 → preview
        handle_message(self.phone, "1", self.contact_id)         # confirm → await_name

        # Пока гость набирает имя — другая бронь занимает те же шконки
        session = WhatsAppSession.objects.get(phone=self.phone)
        preview_ids = session.data["preview_bed_ids"]
        beds = list(Bed.objects.select_related("room").filter(id__in=preview_ids))
        create_booking_with_beds(
            branch_id=self.branch.id,
            beds=beds,
            checkin=self.checkin, checkout=self.checkout,
            name="Race", phone="+996788888888",
            country="KG", purpose=Booking.Purpose.OTHER,
        )

        handle_message(self.phone, "Azat Test", self.contact_id)

        # Наша бронь не создалась; сессия сброшена в START
        sessions_for_phone = Booking.objects.filter(phone="+" + self.phone)
        self.assertEqual(sessions_for_phone.count(), 0)
        session.refresh_from_db()
        self.assertEqual(session.state, WhatsAppSession.State.START)

    @patch("apps.wa_bot.handlers.send_wa_message")
    @patch("apps.bookings.services.notify_new_booking")
    def test_legacy_notify_new_booking_still_called(self, mock_notify, mock_send):
        _make_room(self.branch, "D1", Room.RoomType.DORM_4, 4, 500)

        self._walk_to_private_step(2)
        handle_message(self.phone, "2", self.contact_id)
        handle_message(self.phone, "1", self.contact_id)
        handle_message(self.phone, "1", self.contact_id)
        handle_message(self.phone, "Azat Test", self.contact_id)

        mock_notify.assert_called_once()
        called_booking = mock_notify.call_args.args[0]
        self.assertEqual(called_booking.id, Booking.objects.get().id)
