"""
Команда для создания / обновления начальных номеров хостела.
Запуск: python manage.py seed_rooms

Прайс (актуальный):
  2500 сом — номер с санузлом
  2000 сом — семейный отдельный номер
  1000 сом — койко-место в 4-местном дормитории
   800 сом — койко-место в общем дормитории
"""
from django.core.management.base import BaseCommand
from apps.rooms.models import Room


INITIAL_ROOMS = [
    # ── Номера с санузлом (2500 сом/ночь) ─────────────────────────
    {
        "number": "101",
        "room_type": "Одноместный",
        "capacity": 1,
        "price_per_night": "2500.00",
        "description": "Одноместный номер с собственным санузлом",
    },
    {
        "number": "102",
        "room_type": "Двухместный",
        "capacity": 2,
        "price_per_night": "2500.00",
        "description": "Двухместный номер с собственным санузлом",
    },
    # ── Семейные отдельные номера (2000 сом/ночь) ──────────────────
    {
        "number": "201",
        "room_type": "Семейный",
        "capacity": 4,
        "price_per_night": "2000.00",
        "description": "Семейный номер с отдельным входом",
    },
    {
        "number": "202",
        "room_type": "Семейный",
        "capacity": 4,
        "price_per_night": "2000.00",
        "description": "Семейный номер с отдельным входом",
    },
    # ── Дормитори 4-местный (1000 сом/койко-место) ─────────────────
    {
        "number": "D1",
        "room_type": "Дормитори",
        "capacity": 4,
        "price_per_night": "1000.00",
        "description": "4-местный дормитори, цена за одно койко-место",
    },
    # ── Общий дормитори (800 сом/койко-место) ─────────────────────
    {
        "number": "D2",
        "room_type": "Дормитори",
        "capacity": 8,
        "price_per_night": "800.00",
        "description": "Общий дормитори, 8 мест, цена за одно койко-место",
    },
    {
        "number": "D3",
        "room_type": "Дормитори",
        "capacity": 6,
        "price_per_night": "800.00",
        "description": "Общий дормитори, 6 мест, цена за одно койко-место",
    },
]


class Command(BaseCommand):
    help = "Создаёт / обновляет набор номеров хостела с актуальным прайсом"

    def handle(self, *args, **kwargs):
        created_count = 0
        updated_count = 0

        for data in INITIAL_ROOMS:
            number = data["number"]
            defaults = {k: v for k, v in data.items() if k != "number"}

            obj, created = Room.objects.update_or_create(
                number=number,
                defaults=defaults,
            )

            if created:
                created_count += 1
                self.stdout.write(f"  ✅ создан  №{number} · {obj.room_type} · {obj.price_per_night} сом")
            else:
                updated_count += 1
                self.stdout.write(f"  🔄 обновлён №{number} · {obj.room_type} · {obj.price_per_night} сом")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: создано {created_count}, обновлено {updated_count} номеров"
            )
        )
