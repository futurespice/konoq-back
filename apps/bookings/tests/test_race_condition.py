"""
apps/bookings/tests/test_race_condition.py

Проверяет что create_booking_with_capacity_check не допускает двойной продажи
при конкурентных вызовах.

TransactionTestCase (не TestCase) — чтобы не заворачивать всё в одну
транзакцию, иначе select_for_update() не работает.
"""
import datetime
import threading

from django.db import OperationalError, close_old_connections, connections
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from apps.bookings.models import Booking
from apps.bookings.services import create_booking_with_capacity_check
from apps.rooms.models import Branch, Room


class CapacityCheckTests(TransactionTestCase):
    """Последовательные сценарии — проверяют саму логику capacity."""

    def setUp(self):
        self.branch = Branch.objects.create(name="Test Branch")
        self.room = Room.objects.create(
            branch=self.branch,
            number="T1",
            room_type=Booking.RoomType.DORM_2,
            capacity=2,
            price_per_night=100,
            price_is_per_bed=True,
        )
        self.checkin = datetime.date.today() + datetime.timedelta(days=7)
        self.checkout = self.checkin + datetime.timedelta(days=2)

    def _make(self, guests: int, name: str = "A") -> Booking:
        return create_booking_with_capacity_check(
            branch_id=self.branch.id,
            room_type=Booking.RoomType.DORM_2,
            checkin=self.checkin,
            checkout=self.checkout,
            guests=guests,
            name=name,
            phone="+996700000000",
            country="KG",
            purpose=Booking.Purpose.OTHER,
        )

    def test_creates_booking_when_capacity_available(self):
        b = self._make(guests=1)
        self.assertEqual(b.guests, 1)
        self.assertEqual(b.status, Booking.Status.PENDING)
        self.assertEqual(b.total_price, 200)  # 100 * 1 guest * 2 nights

    def test_rejects_when_no_capacity(self):
        self._make(guests=2)
        with self.assertRaises(ValidationError):
            self._make(guests=1, name="B")

    def test_rejects_past_checkin(self):
        with self.assertRaises(ValidationError):
            create_booking_with_capacity_check(
                branch_id=self.branch.id,
                room_type=Booking.RoomType.DORM_2,
                checkin=datetime.date.today() - datetime.timedelta(days=1),
                checkout=self.checkout,
                guests=1,
                name="A",
                phone="+996700000000",
                country="KG",
                purpose=Booking.Purpose.OTHER,
            )

    def test_rejects_checkout_before_checkin(self):
        with self.assertRaises(ValidationError):
            create_booking_with_capacity_check(
                branch_id=self.branch.id,
                room_type=Booking.RoomType.DORM_2,
                checkin=self.checkout,
                checkout=self.checkin,
                guests=1,
                name="A",
                phone="+996700000000",
                country="KG",
                purpose=Booking.Purpose.OTHER,
            )

    def test_cancelled_bookings_free_capacity(self):
        b1 = self._make(guests=2)
        b1.status = Booking.Status.CANCELLED
        b1.save()
        b2 = self._make(guests=2, name="B")
        self.assertEqual(b2.guests, 2)


class ConcurrentBookingTests(TransactionTestCase):
    """
    Два параллельных create на последнее место — ровно один должен пройти.
    """

    def setUp(self):
        self.branch = Branch.objects.create(name="Test Branch Concurrent")
        Room.objects.create(
            branch=self.branch,
            number="C1",
            room_type=Booking.RoomType.DORM_2,
            capacity=2,
            price_per_night=100,
            price_is_per_bed=True,
        )
        self.checkin = datetime.date.today() + datetime.timedelta(days=10)
        self.checkout = self.checkin + datetime.timedelta(days=2)

    def test_only_one_booking_succeeds_for_last_spots(self):
        barrier = threading.Barrier(2)
        results = {"ok": 0, "rejected": 0, "other": []}
        lock = threading.Lock()

        def attempt(tag: str):
            try:
                barrier.wait(timeout=5)
                create_booking_with_capacity_check(
                    branch_id=self.branch.id,
                    room_type=Booking.RoomType.DORM_2,
                    checkin=self.checkin,
                    checkout=self.checkout,
                    guests=2,
                    name=tag,
                    phone="+996700000000",
                    country="KG",
                    purpose=Booking.Purpose.OTHER,
                )
                with lock:
                    results["ok"] += 1
            except (ValidationError, OperationalError):
                # ValidationError — Postgres-путь (ждали lock, потом capacity full).
                # OperationalError — SQLite-путь (writer не умеет ждать, сразу fail).
                # Оба означают "race поймал второго".
                with lock:
                    results["rejected"] += 1
            except Exception as exc:
                with lock:
                    results["other"].append(repr(exc))
            finally:
                for conn in connections.all():
                    conn.close()
                close_old_connections()

        t1 = threading.Thread(target=attempt, args=("A",))
        t2 = threading.Thread(target=attempt, args=("B",))
        t1.start(); t2.start()
        t1.join(); t2.join()

        self.assertEqual(
            results["other"], [],
            f"Неожиданные исключения: {results['other']}",
        )
        self.assertEqual(
            results["ok"], 1,
            f"Должна была пройти ровно одна бронь, прошло {results['ok']}",
        )
        self.assertEqual(
            results["rejected"], 1,
            f"Ровно одна бронь должна быть отклонена, отклонено {results['rejected']}",
        )
        self.assertEqual(
            Booking.objects.filter(branch_id=self.branch.id).count(), 1,
        )
