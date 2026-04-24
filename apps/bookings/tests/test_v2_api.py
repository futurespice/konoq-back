"""
apps/bookings/tests/test_v2_api.py

HTTP-тесты для Этапа 2b: /api/bookings/v2/, /api/bookings/v2/preview/,
/api/availability/, а также адаптер двойной записи для legacy
/api/bookings/create/.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingBed
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


class V2CreateTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="V2 Branch")
        self.room_dorm = _make_room(
            self.branch, "D1", Room.RoomType.DORM_4, 4, 800, per_bed=True,
        )
        self.checkin = date.today() + timedelta(days=14)
        self.checkout = self.checkin + timedelta(days=2)
        self.base_payload = {
            "branch": self.branch.id,
            "checkin": self.checkin.isoformat(),
            "checkout": self.checkout.isoformat(),
            "fullname": "V2 Guest",
            "phone": "+996700000000",
            "country": "KG",
            "purpose": Booking.Purpose.OTHER,
        }

    def test_v2_create_auto_assign(self):
        payload = {**self.base_payload,
                   "room_type": Room.RoomType.DORM_4,
                   "guests": 2}
        resp = self.client.post(reverse("booking-v2-create"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        body = resp.json()
        self.assertEqual(len(body["beds"]), 2)
        self.assertEqual(body["guests"], 2)

        booking = Booking.objects.get(pk=body["id"])
        self.assertEqual(booking.beds.count(), 2)
        # Новый путь не заполняет Booking.room
        self.assertEqual(booking.room, "")

    def test_v2_create_explicit_beds(self):
        bed_ids = list(self.room_dorm.beds.order_by("label").values_list("id", flat=True))[:3]
        payload = {**self.base_payload, "bed_ids": bed_ids}
        resp = self.client.post(reverse("booking-v2-create"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        body = resp.json()
        self.assertEqual(len(body["beds"]), 3)
        booking = Booking.objects.get(pk=body["id"])
        self.assertEqual(
            sorted(booking.beds.values_list("bed_id", flat=True)),
            sorted(bed_ids),
        )

    def test_v2_create_rejects_both_modes(self):
        bed_ids = list(self.room_dorm.beds.values_list("id", flat=True))[:1]
        payload = {**self.base_payload,
                   "room_type": Room.RoomType.DORM_4,
                   "guests": 1,
                   "bed_ids": bed_ids}
        resp = self.client.post(reverse("booking-v2-create"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_v2_create_rejects_neither_mode(self):
        resp = self.client.post(reverse("booking-v2-create"), self.base_payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class V2PreviewTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Preview Branch")
        _make_room(self.branch, "D1", Room.RoomType.DORM_4, 4, 800, per_bed=True)
        self.checkin = date.today() + timedelta(days=14)
        self.checkout = self.checkin + timedelta(days=3)

    def test_v2_preview_returns_beds_without_creating(self):
        before = Booking.objects.count()
        resp = self.client.post(
            reverse("booking-v2-preview"),
            {
                "branch": self.branch.id,
                "room_type": Room.RoomType.DORM_4,
                "checkin": self.checkin.isoformat(),
                "checkout": self.checkout.isoformat(),
                "guests": 2,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(len(body["beds"]), 2)
        self.assertEqual(body["nights"], 3)
        # 800 × 2 × 3 = 4800
        self.assertEqual(Decimal(str(body["total_price"])), Decimal("4800"))
        self.assertEqual(Booking.objects.count(), before)
        self.assertEqual(BookingBed.objects.count(), 0)

    def test_v2_preview_returns_400_if_no_availability(self):
        resp = self.client.post(
            reverse("booking-v2-preview"),
            {
                "branch": self.branch.id,
                "room_type": Room.RoomType.DORM_4,
                "checkin": self.checkin.isoformat(),
                "checkout": self.checkout.isoformat(),
                "guests": 20,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class AvailabilityEndpointTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Avail Branch")
        _make_room(self.branch, "D1", Room.RoomType.DORM_4, 4, 800, per_bed=True)
        _make_room(self.branch, "S1", Room.RoomType.SINGLE, 1, 2500, per_bed=False)
        self.checkin = date.today() + timedelta(days=14)
        self.checkout = self.checkin + timedelta(days=2)

    def test_availability_endpoint_returns_free_rooms(self):
        resp = self.client.get(
            reverse("availability"),
            {
                "branch": self.branch.id,
                "checkin": self.checkin.isoformat(),
                "checkout": self.checkout.isoformat(),
            },
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        types = {t["room_type"]: t for t in body["types"]}
        self.assertIn(Room.RoomType.DORM_4, types)
        self.assertIn(Room.RoomType.SINGLE, types)
        self.assertEqual(types[Room.RoomType.DORM_4]["total_free_beds"], 4)
        self.assertEqual(types[Room.RoomType.SINGLE]["total_free_beds"], 1)
        opt = types[Room.RoomType.DORM_4]["options"][0]
        self.assertTrue(opt["can_take_whole_room"])


class LegacyAdapterTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.branch = Branch.objects.create(name="Legacy Branch")
        self.checkin = date.today() + timedelta(days=14)
        self.checkout = self.checkin + timedelta(days=2)

    def _post_legacy(self, room_type, guests):
        return self.client.post(
            reverse("booking-create"),
            {
                "fullname": "Legacy Guest",
                "phone": "+996700000000",
                "branch": self.branch.id,
                "room": room_type,
                "checkin": self.checkin.isoformat(),
                "checkout": self.checkout.isoformat(),
                "guests": guests,
                "country": "KG",
                "purpose": Booking.Purpose.OTHER,
            },
            format="json",
        )

    def test_legacy_create_also_creates_bookingbed(self):
        _make_room(self.branch, "L1", Room.RoomType.DORM_4, 4, 800, per_bed=True)
        resp = self._post_legacy(Room.RoomType.DORM_4, 2)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        booking = Booking.objects.get(pk=resp.json()["id"])
        self.assertEqual(booking.room, Room.RoomType.DORM_4)
        self.assertEqual(booking.beds.count(), 2)

    def test_legacy_create_logs_warning_if_no_free_beds(self):
        # Room есть, но Bed-ы не созданы — адаптер не найдёт шконок.
        Room.objects.create(
            branch=self.branch,
            number="L2",
            room_type=Room.RoomType.DORM_4,
            capacity=4,
            price_per_night=800,
            price_is_per_bed=True,
        )
        with self.assertLogs("apps.bookings.services", level="WARNING") as cm:
            resp = self._post_legacy(Room.RoomType.DORM_4, 2)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

        booking = Booking.objects.get(pk=resp.json()["id"])
        self.assertEqual(booking.room, Room.RoomType.DORM_4)
        self.assertEqual(booking.beds.count(), 0)
        self.assertTrue(
            any("legacy booking" in line and "got 0" in line for line in cm.output),
            cm.output,
        )
