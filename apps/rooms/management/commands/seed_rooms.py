"""
Команда для создания начальных номеров хостела.
Запуск: python manage.py seed_rooms
"""
from django.core.management.base import BaseCommand
from apps.rooms.models import Room


INITIAL_ROOMS = [
    {"number": "101", "room_type": "Одноместный", "capacity": 1, "price_per_night": "1200.00", "description": "Тихий номер с видом на двор"},
    {"number": "102", "room_type": "Одноместный", "capacity": 1, "price_per_night": "1200.00", "description": ""},
    {"number": "201", "room_type": "Двухместный", "capacity": 2, "price_per_night": "1800.00", "description": "Просторный номер с двуспальной кроватью"},
    {"number": "202", "room_type": "Двухместный", "capacity": 2, "price_per_night": "1800.00", "description": ""},
    {"number": "301", "room_type": "Семейный",    "capacity": 4, "price_per_night": "2800.00", "description": "Большой семейный номер с отдельной зоной"},
    {"number": "D1",  "room_type": "Дормитори",   "capacity": 6, "price_per_night": "600.00",  "description": "Общий номер, 6 мест"},
    {"number": "D2",  "room_type": "Дормитори",   "capacity": 8, "price_per_night": "600.00",  "description": "Общий номер, 8 мест"},
]


class Command(BaseCommand):
    help = "Создаёт начальный набор номеров хостела"

    def handle(self, *args, **kwargs):
        created = 0
        for data in INITIAL_ROOMS:
            _, was_created = Room.objects.get_or_create(
                number=data["number"],
                defaults=data,
            )
            if was_created:
                created += 1
                self.stdout.write(f"  ✅ №{data['number']} · {data['room_type']}")
            else:
                self.stdout.write(f"  ℹ️  №{data['number']} уже существует")
        self.stdout.write(self.style.SUCCESS(f"\nГотово: создано {created} номеров"))
