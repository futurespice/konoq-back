"""
apps/bookings/tests/test_migration.py

Проверяет data-migration Этапа 1: генерация Bed из Room.capacity и
привязка существующих Booking к шконкам через BookingBed.

Миграции уже применены к тестовой БД до запуска теста — при setUp создаём
свежие Branch/Room/Booking (без Beds), затем вручную вызываем forward-функции
миграций и проверяем что данные сгенерировались корректно.
"""
import datetime
import importlib

from django.apps import apps as global_apps
from django.test import TestCase

from apps.bookings.models import Booking, BookingBed
from apps.rooms.models import Bed, Branch, Room


bed_migration = importlib.import_module("apps.rooms.migrations.0006_bed")
bookingbed_migration = importlib.import_module("apps.bookings.migrations.0007_bookingbed")


class DataMigrationTests(TestCase):

    def test_generates_beds_and_bookingbeds(self):
        branch = Branch.objects.create(name="Test Branch Migration")
        room = Room.objects.create(
            branch=branch,
            number="MIG1",
            room_type=Room.RoomType.DORM_4,
            capacity=4,
            price_per_night=500,
            price_is_per_bed=True,
        )
        checkin = datetime.date.today() + datetime.timedelta(days=30)
        checkout = checkin + datetime.timedelta(days=2)
        booking = Booking.objects.create(
            branch=branch,
            room=Booking.RoomType.DORM_4,
            name="Azat",
            surname="Test",
            phone="+996700000000",
            checkin=checkin,
            checkout=checkout,
            guests=2,
            status=Booking.Status.CONFIRMED,
            country="KG",
            purpose=Booking.Purpose.OTHER,
        )

        bed_migration.generate_beds(global_apps, None)
        bookingbed_migration.backfill_bookingbeds(global_apps, None)

        self.assertEqual(Bed.objects.filter(room=room).count(), 4)
        self.assertEqual(
            BookingBed.objects.filter(booking=booking).count(), 2,
        )
        for bb in BookingBed.objects.filter(booking=booking):
            self.assertEqual(bb.checkin, checkin)
            self.assertEqual(bb.checkout, checkout)
            self.assertEqual(bb.price_per_night, room.price_per_night)
