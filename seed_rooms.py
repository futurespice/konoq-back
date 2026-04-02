"""
seed_rooms.py

Заполняет базу данных реальной структурой номеров обоих филиалов KonoQ.

Запуск:
    python manage.py shell < seed_rooms.py
    # или
    python manage.py runscript seed_rooms   (если установлен django-extensions)

Структура Филиал 1 (Ош) — 13 комнат, 56 мест:
  - 3 комнаты × 4 шконки  (дорм, цена за место)
  - 3 комнаты двухместные вместе (1 с санузлом, 2 без)
  - 2 комнаты двухместные раздельные
  - 2 комнаты × 8 шконок  (дорм, цена за место)
  - 3 комнаты × 6 шконок  (дорм, цена за место)

Итого мест:
  3×4 + 3×2 + 2×2 + 2×8 + 3×6 = 12+6+4+16+18 = 56 ✓
  Комнат: 3+3+2+2+3 = 13 ✓

Структура Филиал 2 — 5 комнат:
  - 2 комнаты с общей кроватью (double_together)
  - 1 комната с отдельными кроватями (double_separate)
  - 1 комната 4 шконки (dorm_4)
  - 1 комната 2 шконки (dorm_2)
"""

from apps.rooms.models import Branch, Room

# ─── Цены (сом) ───────────────────────────────────────────────────────────────
PRICE_BED_DORM    = 600    # за место в дорме (любой размер)
PRICE_DOUBLE_STD  = 1500   # двухместная без санузла (вся комната)
PRICE_DOUBLE_BATH = 2000   # двухместная с санузлом

# ─── Создаём / обновляем филиалы ─────────────────────────────────────────────
branch1, _ = Branch.objects.update_or_create(
    name="Филиал 1 — Ош",
    defaults={
        "address":   "г. Ош, KonoQ Hostel",
        "is_active": True,
    },
)

branch2, _ = Branch.objects.update_or_create(
    name="Филиал 2",
    defaults={
        "address":   "",
        "is_active": True,
    },
)

print(f"Филиалы: {branch1} | {branch2}")

# ─── Вспомогательная функция ─────────────────────────────────────────────────
def seed_room(branch, number, room_type, capacity, price, per_bed=False, bathroom=False, description=""):
    room, created = Room.objects.update_or_create(
        number=number,
        defaults=dict(
            branch=branch,
            room_type=room_type,
            capacity=capacity,
            price_per_night=price,
            price_is_per_bed=per_bed,
            has_bathroom=bathroom,
            description=description,
            is_active=True,
        ),
    )
    action = "Создан" if created else "Обновлён"
    print(f"  {action}: {room}")
    return room

# ═══════════════════════════════════════════════════════════════════════════════
# ФИЛИАЛ 1 — ОШ
# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Филиал 1 (Ош) ──")

# 3 комнаты × 4 шконки
for i, num in enumerate(["101", "102", "103"], start=1):
    seed_room(branch1, num, Room.RoomType.DORM_4, 4, PRICE_BED_DORM, per_bed=True)

# 3 комнаты двухместные вместе (первая — с санузлом)
seed_room(branch1, "104", Room.RoomType.DOUBLE_TOGETHER, 2, PRICE_DOUBLE_BATH,
          bathroom=True, description="Двухместная с общей кроватью, собственный санузел")
seed_room(branch1, "105", Room.RoomType.DOUBLE_TOGETHER, 2, PRICE_DOUBLE_STD)
seed_room(branch1, "106", Room.RoomType.DOUBLE_TOGETHER, 2, PRICE_DOUBLE_STD)

# 2 комнаты двухместные раздельные
seed_room(branch1, "107", Room.RoomType.DOUBLE_SEPARATE, 2, PRICE_DOUBLE_STD)
seed_room(branch1, "108", Room.RoomType.DOUBLE_SEPARATE, 2, PRICE_DOUBLE_STD)

# 2 комнаты × 8 шконок
seed_room(branch1, "109", Room.RoomType.DORM_8, 8, PRICE_BED_DORM, per_bed=True)
seed_room(branch1, "110", Room.RoomType.DORM_8, 8, PRICE_BED_DORM, per_bed=True)

# 3 комнаты × 6 шконок
seed_room(branch1, "111", Room.RoomType.DORM_6, 6, PRICE_BED_DORM, per_bed=True)
seed_room(branch1, "112", Room.RoomType.DORM_6, 6, PRICE_BED_DORM, per_bed=True)
seed_room(branch1, "113", Room.RoomType.DORM_6, 6, PRICE_BED_DORM, per_bed=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ФИЛИАЛ 2
# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Филиал 2 ──")

# 2 комнаты с общей кроватью
seed_room(branch2, "201", Room.RoomType.DOUBLE_TOGETHER, 2, PRICE_DOUBLE_STD)
seed_room(branch2, "202", Room.RoomType.DOUBLE_TOGETHER, 2, PRICE_DOUBLE_STD)

# 1 комната с отдельными кроватями
seed_room(branch2, "203", Room.RoomType.DOUBLE_SEPARATE, 2, PRICE_DOUBLE_STD)

# 1 комната 4 шконки
seed_room(branch2, "204", Room.RoomType.DORM_4, 4, PRICE_BED_DORM, per_bed=True)

# 1 комната 2 шконки
seed_room(branch2, "205", Room.RoomType.DORM_2, 2, PRICE_BED_DORM, per_bed=True)

# ─── Итог ─────────────────────────────────────────────────────────────────────
print("\n══ Итог ══")
for branch in [branch1, branch2]:
    rooms = Room.objects.filter(branch=branch, is_active=True)
    total_capacity = sum(r.capacity for r in rooms)
    print(f"{branch.name}: {rooms.count()} комнат, {total_capacity} мест")

print("\nГотово! Seed завершён.")
