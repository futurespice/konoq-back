"""
apps/bookings/tests/test_notifications.py

Часть A Этапа 3a: WA-уведомление о смене статуса брони уходит через
transaction.on_commit, а не из pre_save signal + threading.Thread.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase

from apps.bookings.models import Booking
from apps.bookings.services import update_booking_status
from apps.rooms.models import Branch
from apps.wa_bot.models import WhatsAppSession


class StatusChangeNotificationTests(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Notif Branch")
        self.session = WhatsAppSession.objects.create(
            phone="996700000000",
            data={"contact_id": "contact-123"},
            lang=WhatsAppSession.Lang.RU,
        )
        self.booking = Booking.objects.create(
            branch=self.branch,
            name="Azat", surname="Test",
            phone="+996700000000",
            checkin=date.today() + timedelta(days=7),
            checkout=date.today() + timedelta(days=9),
            guests=1,
            source=Booking.Source.WHATSAPP,
            status=Booking.Status.PENDING,
            country="KG",
            purpose=Booking.Purpose.OTHER,
        )

    @patch("apps.wa_bot.sendpulse_api.send_wa_message")
    def test_confirm_triggers_wa_message(self, mock_send):
        with self.captureOnCommitCallbacks(execute=True):
            update_booking_status(
                booking_id=self.booking.id,
                new_status=Booking.Status.CONFIRMED,
            )

        mock_send.assert_called_once()
        phone, msg, contact_id = mock_send.call_args.args
        self.assertEqual(phone, "+996700000000")
        self.assertEqual(contact_id, "contact-123")
        self.assertIn("подтверждена", msg)

    @patch("apps.wa_bot.sendpulse_api.send_wa_message")
    def test_cancel_triggers_wa_message(self, mock_send):
        with self.captureOnCommitCallbacks(execute=True):
            update_booking_status(
                booking_id=self.booking.id,
                new_status=Booking.Status.CANCELLED,
            )

        mock_send.assert_called_once()
        _, msg, _ = mock_send.call_args.args
        self.assertIn("отклонена", msg)

    @patch("apps.wa_bot.sendpulse_api.send_wa_message")
    def test_same_status_no_notification(self, mock_send):
        with self.captureOnCommitCallbacks(execute=True):
            update_booking_status(
                booking_id=self.booking.id,
                new_status=Booking.Status.PENDING,
            )
        mock_send.assert_not_called()

    @patch("apps.wa_bot.sendpulse_api.send_wa_message")
    def test_non_whatsapp_booking_no_notification(self, mock_send):
        self.booking.source = Booking.Source.DIRECT
        self.booking.save(update_fields=["source"])

        with self.captureOnCommitCallbacks(execute=True):
            update_booking_status(
                booking_id=self.booking.id,
                new_status=Booking.Status.CONFIRMED,
            )
        mock_send.assert_not_called()

    @patch("apps.wa_bot.sendpulse_api.send_wa_message")
    def test_rollback_prevents_wa_message(self, mock_send):
        try:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    update_booking_status(
                        booking_id=self.booking.id,
                        new_status=Booking.Status.CONFIRMED,
                    )
                    raise RuntimeError("rollback")
        except RuntimeError:
            pass

        mock_send.assert_not_called()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    @patch(
        "apps.wa_bot.sendpulse_api.send_wa_message",
        side_effect=Exception("SendPulse down"),
    )
    def test_send_wa_failure_does_not_break_status_update(self, mock_send):
        with self.assertLogs("apps.bookings.services", level="ERROR") as cm:
            with self.captureOnCommitCallbacks(execute=True):
                update_booking_status(
                    booking_id=self.booking.id,
                    new_status=Booking.Status.CONFIRMED,
                )

        mock_send.assert_called_once()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertTrue(
            any("WA status-change notify failed" in line for line in cm.output),
            cm.output,
        )
