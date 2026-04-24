"""
apps/rooms/management/commands/seed_prices.py

Проставить актуальные цены по комнатам (прайс апрель 2026).

Запуск:
    python manage.py seed_prices         # применить и вывести diff
    python manage.py seed_prices --dry   # только показать что изменится

Категории и цены — см. docs/bed-level-booking.md §Вопрос 4.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.rooms.models import Room


# room_number -> (price, price_is_per_bed, human_label)
# Если в БД добавятся новые комнаты — дописать сюда.
PRICES: dict[str, tuple[Decimal, bool, str]] = {
    # ── Главный филиал ────────────────────────────────────────────────────
    "104":  (Decimal("2500"), False, "Вип — с санузлом"),
    "105":  (Decimal("2000"), False, "Семейный"),
    "106":  (Decimal("2000"), False, "Семейный"),
    "107":  (Decimal("2000"), False, "Двухместный раздельный"),
    "108":  (Decimal("2000"), False, "Двухместный раздельный"),
    "101":  (Decimal("800"),  True,  "Дорм-4"),
    "102":  (Decimal("800"),  True,  "Дорм-4"),
    "103":  (Decimal("800"),  True,  "Дорм-4"),
    "109":  (Decimal("800"),  True,  "Дорм-8"),
    "1010": (Decimal("800"),  True,  "Дорм-8"),
    "111":  (Decimal("800"),  True,  "Дорм-6"),
    "112":  (Decimal("800"),  True,  "Дорм-6"),
    "113":  (Decimal("800"),  True,  "Дорм-6"),

    # ── Второй филиал ─────────────────────────────────────────────────────
    "201":  (Decimal("2000"), False, "Семейный"),
    "202":  (Decimal("2000"), False, "Семейный"),
    "203":  (Decimal("1500"), False, "Одноместная (дефолт, не в прайсе)"),
    "204":  (Decimal("800"),  True,  "Дорм-4"),
    "205":  (Decimal("800"),  True,  "Дорм-2"),
}


class Command(BaseCommand):
    help = "Обновляет price_per_night и price_is_per_bed на комнатах по текущему прайсу"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry",
            action="store_true",
            help="Только показать что изменится, без записи в БД",
        )

    def handle(self, *args, **options):
        dry = options["dry"]

        changes: list[str] = []
        missing: list[str] = []
        unchanged = 0

        with transaction.atomic():
            for number, (new_price, new_per_bed, label) in PRICES.items():
                try:
                    room = Room.objects.select_for_update().get(number=number)
                except Room.DoesNotExist:
                    missing.append(number)
                    continue

                old_price = room.price_per_night
                old_per_bed = room.price_is_per_bed

                if old_price == new_price and old_per_bed == new_per_bed:
                    unchanged += 1
                    continue

                diff = (
                    f"  #{number:5s}  "
                    f"{old_price}→{new_price} сом  "
                    f"per_bed={old_per_bed}→{new_per_bed}  "
                    f"[{label}]"
                )
                changes.append(diff)

                if not dry:
                    room.price_per_night = new_price
                    room.price_is_per_bed = new_per_bed
                    room.save(update_fields=["price_per_night", "price_is_per_bed"])

            if dry:
                # В dry-режиме откатываем транзакцию чтобы SELECT FOR UPDATE
                # не задержал никого
                transaction.set_rollback(True)

        # ── Отчёт ─────────────────────────────────────────────────────────
        self.stdout.write("")
        if changes:
            verb = "ИЗМЕНИТСЯ" if dry else "ОБНОВЛЕНО"
            self.stdout.write(self.style.SUCCESS(f"{verb} ({len(changes)}):"))
            for line in changes:
                self.stdout.write(line)
        else:
            self.stdout.write(self.style.SUCCESS("Всё уже актуально, менять нечего."))

        if unchanged:
            self.stdout.write(f"\nБез изменений: {unchanged}")

        if missing:
            self.stdout.write(self.style.WARNING(
                f"\nНе найдены в БД ({len(missing)}): {', '.join(missing)}"
            ))

        if dry:
            self.stdout.write(self.style.NOTICE("\n--dry: ничего не записано."))
