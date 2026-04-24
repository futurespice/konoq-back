# Исправить race condition при бронировании

Конкретная команда для устранения самой критичной проблемы проекта: двойное
бронирование одного места.

## Контекст

Сейчас бронирование создаётся в трёх местах без защиты от конкурентных запросов:
- `apps/bookings/views.py::BookingCreateView.post` — прямое создание через сайт
- `apps/wa_bot/handlers.py::_handle_name` — через WhatsApp-бот
- iCal sync (в `apps/bookings/management/commands/` если есть) — импорт извне

Все три пути могут одновременно пройти проверку `current_booked + guests <= capacity` и
создать бронь на одно место.

## Цель

**Одна точка создания бронирования** — сервис с правильной блокировкой. Все три входа
вызывают его.

## План (Goal-Driven):

```
1. Создать apps/bookings/selectors.py::get_booked_guests_by_type → verify: функция
   возвращает dict {room_type: total_guests} для пересечения дат
2. Создать apps/bookings/services.py::create_booking_with_capacity_check → verify:
   внутри transaction.atomic() + select_for_update на Room + проверка + create
3. Перевести BookingCreateSerializer на вызов сервиса → verify: тест конкурентного
   создания двух броней на последнее место — одна 201, другая 400
4. Перевести wa_bot/handlers.py::_handle_name на вызов сервиса → verify: убран прямой
   Booking.objects.create
5. Удалить apps/rooms/views.py::_get_booked_guests (перенесено в selectors) → verify:
   `grep -r "_get_booked_guests" apps/` ничего не находит кроме selectors.py
6. Убрать логику цены из Booking.save() (уже переносится в сервис) → verify:
   Booking.save() чистый super().save()
```

## Шаги детально:

### 1. `apps/bookings/selectors.py` (создать файл)

```python
"""apps/bookings/selectors.py"""
from datetime import date
from django.db.models import Sum
from .models import Booking


def get_booked_guests_by_type(
    *, checkin: date, checkout: date, branch_id: int | None = None,
) -> dict[str, int]:
    """
    Суммарное число гостей в пересекающихся с периодом бронях по типу комнаты.
    Учитывает только активные брони (pending + confirmed).
    """
    qs = Booking.objects.filter(
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
        checkin__lt=checkout,
        checkout__gt=checkin,
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return {
        row["room"]: row["total_guests"]
        for row in qs.values("room").annotate(total_guests=Sum("guests"))
    }
```

### 2. `apps/bookings/services.py` (создать файл)

```python
"""apps/bookings/services.py"""
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.rooms.models import Room
from .models import Booking


def calculate_booking_price(
    *, room: Room, guests: int, nights: int,
) -> tuple[Decimal, Decimal]:
    per_night = (
        room.price_per_night * guests
        if room.price_is_per_bed
        else room.price_per_night
    )
    total = per_night * Decimal(max(nights, 0))
    return per_night, total


def create_booking_with_capacity_check(
    *,
    branch_id: int,
    room_type: str,
    checkin: date,
    checkout: date,
    guests: int,
    name: str,
    surname: str = "",
    phone: str,
    source: str = Booking.Source.DIRECT,
    **extra_fields,
) -> Booking:
    # ── Guard-проверки ДО atomic ────────────────────────────────────────────
    if checkin >= checkout:
        raise ValidationError({"checkout": "Дата выезда должна быть позже заезда."})
    if checkin < date.today():
        raise ValidationError({"checkin": "Дата заезда не может быть в прошлом."})
    if guests < 1 or guests > 20:
        raise ValidationError({"guests": "Количество гостей должно быть от 1 до 20."})

    # ── Критическая секция с блокировкой ────────────────────────────────────
    with transaction.atomic():
        rooms = list(
            Room.objects
                .select_for_update()
                .filter(branch_id=branch_id, room_type=room_type, is_active=True)
        )
        if not rooms:
            raise ValidationError("Нет активных номеров этого типа.")

        total_capacity = sum(r.capacity for r in rooms)

        booked = Booking.objects.filter(
            branch_id=branch_id,
            room=room_type,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
            checkin__lt=checkout,
            checkout__gt=checkin,
        ).aggregate(s=Sum("guests"))["s"] or 0

        if booked + guests > total_capacity:
            raise ValidationError("Нет свободных мест на эти даты.")

        # Цена — из любой комнаты этого типа (все они одной цены по дизайну)
        nights = (checkout - checkin).days
        per_night, total = calculate_booking_price(
            room=rooms[0], guests=guests, nights=nights,
        )

        return Booking.objects.create(
            branch_id=branch_id,
            room=room_type,
            checkin=checkin,
            checkout=checkout,
            guests=guests,
            name=name,
            surname=surname,
            phone=phone,
            source=source,
            price_per_night=per_night,
            total_price=total,
            **extra_fields,
        )
```

### 3. `apps/bookings/serializers.py::BookingCreateSerializer`

В `create(self, validated_data)` замени `Booking.objects.create(...)` на
`create_booking_with_capacity_check(**validated_data)`. Или вынеси вызов сервиса в
`BookingCreateView.perform_create`.

### 4. `apps/wa_bot/handlers.py::_handle_name`

Удали inline проверку capacity + `Booking.objects.create(...)`. Замени на:
```python
from apps.bookings.services import create_booking_with_capacity_check

try:
    b = create_booking_with_capacity_check(
        branch_id=branch_id,
        room_type=r_type,
        checkin=checkin_obj,
        checkout=checkout_obj,
        guests=guests_n,
        name=name,
        surname=surname,
        phone="+" + phone if not phone.startswith("+") else phone,
        source=Booking.Source.WHATSAPP,
        country="Chat WhatsApp",
        purpose=Booking.Purpose.OTHER,
        status=Booking.Status.PENDING,
    )
except ValidationError:
    _reset_session(session, keep_lang=True)
    _send(phone, _t(session, 'no_availability'), session)
    return
```

### 5. Удалить дубли

- `apps/rooms/views.py::_get_booked_guests` — удалить, обновить импорты
- `apps/bookings/models.py::Booking.save()` — убрать логику цены, оставить чистый
  `super().save(*args, **kwargs)`

### 6. Тест (обязательно)

`apps/bookings/tests/test_race_condition.py`:
```python
import threading
from django.test import TransactionTestCase
from apps.bookings.services import create_booking_with_capacity_check

class TestConcurrentBooking(TransactionTestCase):
    def test_only_one_booking_succeeds_for_last_spot(self):
        # Создаём комнату с capacity=2, уже забронировано 1 место
        # Запускаем два параллельных create на guests=2 → должен пройти только один
        ...
```

Нужен `TransactionTestCase` (не `TestCase`), потому что `TestCase` заворачивает всё
в одну транзакцию и блокировки не работают.

## Verify

После выполнения:
```bash
python manage.py test apps.bookings.tests.test_race_condition -v 2
grep -rn "Booking.objects.create" apps/  # должно остаться только в services.py
grep -rn "_get_booked_guests" apps/       # должно найти только в selectors.py
```

Затем запусти `/review apps/bookings/` — должен вернуть **APPROVE** по race-condition
пункту.
