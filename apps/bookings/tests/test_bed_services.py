"""
apps/bookings/tests/test_bed_services.py

Тесты bed-level сервисов Этапа 2a: auto_assign_beds, create_booking_with_beds,
get_available_beds (интеграционно), calculate_booking_total.
"""
import threading
from datetime import date, timedelta
from decimal import Decimal

from django.db import OperationalError, close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import ValidationError

from apps.bookings.models import Booking
from apps.bookings.selectors import get_available_beds
from apps.bookings.services import (
    auto_assign_beds,
    calculate_booking_total,
    create_booking_with_beds,
)
from apps.rooms.models import Bed, Branch, Room


def _make_room(branch, number, room_type, capacity, price, *, per_bed=True):
    room = Room.objects.create(
        branch=branch,
        number=number,
        room_type=room_type,
        capacity=capacity,
        price_per_night=price,
        price_is_per_bed=per_bed,
    )
    for i in range(1, capacity + 1):
        Bed.objects.create(room=room, label=str(i))
    return room


def _create_booking(beds, checkin, checkout, *, is_private=False, name="Azat"):
    branch_id = beds[0].room.branch_id
    return create_booking_with_beds(
        branch_id=branch_id,
        beds=list(beds),
        checkin=checkin,
        checkout=checkout,
        is_private_booking=is_private,
        name=name,
        phone="+996700000000",
        country="KG",
        purpose=Booking.Purpose.OTHER,
    )


class AutoAssignBedsTests(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Auto Branch")
        self.checkin = date.today() + timedelta(days=7)
        self.checkout = self.checkin + timedelta(days=2)

    def test_auto_assign_returns_beds_from_same_room_preferably(self):
        _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 500)
        r6 = _make_room(self.branch, "D6", Room.RoomType.DORM_6, 6, 500)

        beds = auto_assign_beds(
            branch_id=self.branch.id,
            room_type=Room.RoomType.DORM_6,
            checkin=self.checkin,
            checkout=self.checkout,
            guests=3,
        )
        self.assertEqual(len(beds), 3)
        self.assertEqual({b.room_id for b in beds}, {r6.id})

    def test_auto_assign_private_returns_whole_room(self):
        r = _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 500)
        beds = auto_assign_beds(
            branch_id=self.branch.id,
            room_type=Room.RoomType.DORM_4,
            checkin=self.checkin,
            checkout=self.checkout,
            guests=4,
            want_private_room=True,
        )
        self.assertEqual(len(beds), 4)
        self.assertEqual({b.room_id for b in beds}, {r.id})

    def test_auto_assign_private_fails_if_no_whole_room_free(self):
        r = _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 500)
        first_bed = r.beds.order_by("label").first()
        _create_booking([first_bed], self.checkin, self.checkout)

        with self.assertRaises(ValidationError):
            auto_assign_beds(
                branch_id=self.branch.id,
                room_type=Room.RoomType.DORM_4,
                checkin=self.checkin,
                checkout=self.checkout,
                guests=4,
                want_private_room=True,
            )

    def test_auto_assign_fails_if_not_enough_beds(self):
        _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 500)
        with self.assertRaises(ValidationError):
            auto_assign_beds(
                branch_id=self.branch.id,
                room_type=Room.RoomType.DORM_4,
                checkin=self.checkin,
                checkout=self.checkout,
                guests=10,
            )

    def test_checkin_equals_checkout_rejected(self):
        _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 500)
        with self.assertRaises(ValidationError):
            auto_assign_beds(
                branch_id=self.branch.id,
                room_type=Room.RoomType.DORM_4,
                checkin=self.checkin,
                checkout=self.checkin,
                guests=1,
            )

    def test_checkin_in_past_rejected(self):
        _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 500)
        with self.assertRaises(ValidationError):
            auto_assign_beds(
                branch_id=self.branch.id,
                room_type=Room.RoomType.DORM_4,
                checkin=date.today() - timedelta(days=1),
                checkout=date.today() + timedelta(days=1),
                guests=1,
            )


class CreateBookingWithBedsTests(TestCase):

    def setUp(self):
        self.branch = Branch.objects.create(name="Create Branch")
        self.checkin = date.today() + timedelta(days=7)
        self.checkout = self.checkin + timedelta(days=3)  # 3 ночи

    def test_create_booking_stores_price_snapshot(self):
        r = _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 800)
        beds = list(r.beds.order_by("label"))[:2]
        booking = _create_booking(beds, self.checkin, self.checkout)

        bb = booking.beds.first()
        self.assertEqual(bb.price_per_night, Decimal("800.00"))

        r.price_per_night = Decimal("999.00")
        r.save(update_fields=["price_per_night"])

        bb.refresh_from_db()
        self.assertEqual(bb.price_per_night, Decimal("800.00"))

    def test_create_booking_total_price_dorm(self):
        r = _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 800, per_bed=True)
        beds = list(r.beds.order_by("label"))[:2]
        booking = _create_booking(beds, self.checkin, self.checkout)
        # 800 * 2 шконки * 3 ночи = 4800
        self.assertEqual(booking.total_price, Decimal("4800.00"))

    def test_create_booking_total_price_private(self):
        r = _make_room(
            self.branch, "P1", Room.RoomType.DOUBLE_TOGETHER,
            2, 2500, per_bed=False,
        )
        beds = list(r.beds.order_by("label"))
        booking = _create_booking(beds, self.checkin, self.checkout)
        # 2500 * 3 ночи = 7500 (НЕ 2500 * 2 * 3)
        self.assertEqual(booking.total_price, Decimal("7500.00"))

    def test_create_booking_rejects_mixed_price_modes(self):
        r1 = _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 800, per_bed=True)
        r2 = _make_room(self.branch, "S1", Room.RoomType.SINGLE, 1, 2500, per_bed=False)
        beds = [r1.beds.first(), r2.beds.first()]
        with self.assertRaises(ValidationError):
            _create_booking(beds, self.checkin, self.checkout)

    def test_private_booking_blocks_remaining_beds(self):
        r = _make_room(self.branch, "D4", Room.RoomType.DORM_4, 4, 800)
        beds = list(r.beds.order_by("label"))[:2]
        _create_booking(beds, self.checkin, self.checkout, is_private=True)

        free = get_available_beds(
            branch_id=self.branch.id,
            checkin=self.checkin,
            checkout=self.checkout,
        ).filter(room=r).count()
        self.assertEqual(free, 0)


class ConcurrentCreateBookingTests(TransactionTestCase):
    """
    Два потока пытаются занять одни и те же последние шконки — должен
    успеть ровно один.
    """

    def setUp(self):
        self.branch = Branch.objects.create(name="Concurrent Branch")
        self.room = Room.objects.create(
            branch=self.branch,
            number="C1",
            room_type=Room.RoomType.DORM_2,
            capacity=2,
            price_per_night=500,
            price_is_per_bed=True,
        )
        for i in (1, 2):
            Bed.objects.create(room=self.room, label=str(i))
        self.checkin = date.today() + timedelta(days=10)
        self.checkout = self.checkin + timedelta(days=2)

    def test_concurrent_create_only_one_succeeds(self):
        bed_ids = list(self.room.beds.values_list("id", flat=True))
        barrier = threading.Barrier(2)
        results = {"ok": 0, "rejected": 0, "other": []}
        lock = threading.Lock()

        def attempt(tag: str):
            try:
                barrier.wait(timeout=5)
                beds = list(
                    Bed.objects
                        .select_related("room")
                        .filter(id__in=bed_ids)
                )
                create_booking_with_beds(
                    branch_id=self.branch.id,
                    beds=beds,
                    checkin=self.checkin,
                    checkout=self.checkout,
                    name=tag,
                    phone="+996700000000",
                    country="KG",
                    purpose=Booking.Purpose.OTHER,
                )
                with lock:
                    results["ok"] += 1
            except (ValidationError, OperationalError):
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

        self.assertEqual(results["other"], [], f"Unexpected: {results['other']}")
        self.assertEqual(results["ok"], 1)
        self.assertEqual(results["rejected"], 1)
        self.assertEqual(Booking.objects.filter(branch_id=self.branch.id).count(), 1)
