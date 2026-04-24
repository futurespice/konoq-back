# Написать тесты

Напиши тесты для `$ARGUMENTS`.

## Формат `$ARGUMENTS`:
- `apps/<module>/services.py` — тесты сервисов
- `apps/<module>/views.py` — тесты API
- `apps/<module>/selectors.py::<function>` — тесты конкретной функции
- `apps/<module>/` — всё покрытие модуля

## Стек тестов в проекте

- `django.test.TestCase` — обычные (обёрнуты в одну транзакцию)
- `django.test.TransactionTestCase` — **обязательно** когда тестируем
  `select_for_update` или конкурентность (см. раздел "Race condition" ниже)
- `rest_framework.test.APIClient` — для API-тестов
- **Нет** `pytest`, `pytest-django`, `factory_boy` в проекте — не добавляй их без
  явной просьбы. Используй чистый `django.test` и ручные `Model.objects.create(...)`
  для fixtures.

## Структура

Каждый модуль имеет папку `apps/<module>/tests/`:
```
apps/<module>/tests/
├── __init__.py
├── test_services.py      # приоритет — тестируй сервисы первым
├── test_selectors.py     # если есть selectors с нетривиальной фильтрацией
├── test_api.py           # HTTP-слой: auth, permissions, 200/400/403/404
└── test_race.py          # TransactionTestCase для конкурентных сценариев
```

Если папки `tests/` нет — создай вместо `tests.py` (Django поддерживает оба, но
папка удобнее).

---

## Шаблоны:

### Services (приоритет)

```python
# apps/<module>/tests/test_services.py
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.rooms.models import Branch, Room
from apps.bookings.models import Booking
from apps.bookings.services import create_booking_with_capacity_check


class CreateBookingServiceTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Test Branch")
        self.room = Room.objects.create(
            branch=self.branch,
            number="101",
            room_type=Room.RoomType.DORM_4,
            capacity=4,
            price_per_night=Decimal("500"),
            price_is_per_bed=True,
        )
        self.base_kwargs = dict(
            branch_id=self.branch.id,
            room_type=Room.RoomType.DORM_4,
            checkin=date.today() + timedelta(days=1),
            checkout=date.today() + timedelta(days=3),
            guests=2,
            name="Ivan",
            phone="+996700000000",
        )

    def test_creates_booking_with_correct_total(self):
        booking = create_booking_with_capacity_check(**self.base_kwargs)

        # 500 * 2 гостей * 2 ночи = 2000
        self.assertEqual(booking.price_per_night, Decimal("1000"))
        self.assertEqual(booking.total_price, Decimal("2000"))
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_rejects_when_checkout_before_checkin(self):
        kwargs = {**self.base_kwargs, "checkout": self.base_kwargs["checkin"]}
        with self.assertRaises(ValidationError):
            create_booking_with_capacity_check(**kwargs)

    def test_rejects_when_no_free_spots(self):
        # Забиваем всю вместимость — 4 места
        Booking.objects.create(
            branch=self.branch, room=Room.RoomType.DORM_4,
            checkin=self.base_kwargs["checkin"],
            checkout=self.base_kwargs["checkout"],
            guests=4, status=Booking.Status.CONFIRMED,
            name="Filler", phone="+1",
            country="X", purpose=Booking.Purpose.OTHER,
        )
        with self.assertRaises(ValidationError):
            create_booking_with_capacity_check(**self.base_kwargs)

    def test_cancelled_bookings_do_not_count_toward_capacity(self):
        # Отменённая бронь не занимает место
        Booking.objects.create(
            branch=self.branch, room=Room.RoomType.DORM_4,
            checkin=self.base_kwargs["checkin"],
            checkout=self.base_kwargs["checkout"],
            guests=4, status=Booking.Status.CANCELLED,
            name="Cancelled", phone="+1",
            country="X", purpose=Booking.Purpose.OTHER,
        )
        booking = create_booking_with_capacity_check(**self.base_kwargs)
        self.assertIsNotNone(booking.id)

    def test_price_zero_is_valid(self):
        """Баг с нулём: price=0 — валидное значение, не должно переопределяться."""
        self.room.price_per_night = Decimal("0")
        self.room.save()

        booking = create_booking_with_capacity_check(**self.base_kwargs)
        self.assertEqual(booking.total_price, Decimal("0"))
```

### Selectors

```python
# apps/bookings/tests/test_selectors.py
from datetime import date, timedelta
from django.test import TestCase
from apps.rooms.models import Branch
from apps.bookings.models import Booking
from apps.bookings.selectors import get_booked_guests_by_type


class GetBookedGuestsByTypeTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="B")

    def _booking(self, checkin_offset, checkout_offset, guests, status, room):
        return Booking.objects.create(
            branch=self.branch, room=room, guests=guests, status=status,
            checkin=date.today() + timedelta(days=checkin_offset),
            checkout=date.today() + timedelta(days=checkout_offset),
            name="X", phone="+1", country="X",
            purpose=Booking.Purpose.OTHER,
        )

    def test_counts_overlapping_only(self):
        self._booking(1, 3, 2, Booking.Status.CONFIRMED, "dorm_4")
        self._booking(5, 7, 3, Booking.Status.CONFIRMED, "dorm_4")  # не пересекается

        result = get_booked_guests_by_type(
            checkin=date.today() + timedelta(days=2),
            checkout=date.today() + timedelta(days=4),
            branch_id=self.branch.id,
        )
        self.assertEqual(result.get("dorm_4"), 2)

    def test_excludes_cancelled(self):
        self._booking(1, 3, 2, Booking.Status.CANCELLED, "dorm_4")
        result = get_booked_guests_by_type(
            checkin=date.today() + timedelta(days=1),
            checkout=date.today() + timedelta(days=3),
            branch_id=self.branch.id,
        )
        self.assertEqual(result.get("dorm_4"), None)

    def test_includes_pending(self):
        self._booking(1, 3, 2, Booking.Status.PENDING, "dorm_4")
        result = get_booked_guests_by_type(
            checkin=date.today() + timedelta(days=1),
            checkout=date.today() + timedelta(days=3),
            branch_id=self.branch.id,
        )
        self.assertEqual(result.get("dorm_4"), 2)
```

### API views

```python
# apps/<module>/tests/test_api.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import User


class BookingListAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_user(
            username="m", password="p", role=User.Role.MANAGER,
        )
        self.admin = User.objects.create_user(
            username="a", password="p", role=User.Role.ADMIN,
        )

    def test_requires_authentication(self):
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, 401)

    def test_manager_can_list(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, 200)

    def test_filters_by_status(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/bookings/?status=pending")
        self.assertEqual(response.status_code, 200)


class FinanceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_user(
            username="m", password="p", role=User.Role.MANAGER,
        )
        self.admin = User.objects.create_user(
            username="a", password="p", role=User.Role.ADMIN,
        )

    def test_manager_forbidden_from_finance(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/finance/summary/")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_finance(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/finance/summary/")
        self.assertEqual(response.status_code, 200)
```

### Race condition (TransactionTestCase обязательно)

```python
# apps/bookings/tests/test_race.py
import threading
from decimal import Decimal
from datetime import date, timedelta

from django.db import connection
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from apps.rooms.models import Branch, Room
from apps.bookings.models import Booking
from apps.bookings.services import create_booking_with_capacity_check


class ConcurrentBookingTests(TransactionTestCase):
    """
    Используем TransactionTestCase, а не TestCase — иначе select_for_update
    не работает (обычный TestCase оборачивает всё в одну транзакцию).
    """

    def setUp(self):
        self.branch = Branch.objects.create(name="B")
        self.room = Room.objects.create(
            branch=self.branch, number="1",
            room_type=Room.RoomType.SINGLE,
            capacity=1,
            price_per_night=Decimal("100"),
        )
        self.kwargs = dict(
            branch_id=self.branch.id,
            room_type=Room.RoomType.SINGLE,
            checkin=date.today() + timedelta(days=1),
            checkout=date.today() + timedelta(days=2),
            guests=1,
            phone="+1",
        )

    def test_only_one_of_two_concurrent_bookings_succeeds(self):
        results = []
        errors = []

        def _book(name):
            try:
                b = create_booking_with_capacity_check(
                    name=name, **self.kwargs,
                )
                results.append(b.id)
            except ValidationError as e:
                errors.append(str(e))
            finally:
                connection.close()

        t1 = threading.Thread(target=_book, args=("A",))
        t2 = threading.Thread(target=_book, args=("B",))
        t1.start(); t2.start()
        t1.join();  t2.join()

        self.assertEqual(len(results), 1, f"ожидали 1 успех, получили {len(results)}")
        self.assertEqual(len(errors), 1)
        self.assertEqual(Booking.objects.count(), 1)
```

---

## Обязательные edge cases для Konoq

Каждый сервис брони должен покрывать:
- ✅ `checkin == checkout` → `ValidationError`
- ✅ `checkin` в прошлом → `ValidationError`
- ✅ `guests = 0` или `> 20` → `ValidationError`
- ✅ `price_per_night = 0` → валидно, total тоже 0 (баг с нулём!)
- ✅ Отменённая бронь не занимает место
- ✅ `pending` занимает место
- ✅ Пересечение через дату `checkin` равную `checkout` другой брони — не пересекается
  (`checkin__lt=other.checkout` — строго меньше)
- ✅ Дорм с `price_is_per_bed=True` → цена умножается на `guests`
- ✅ Обычная комната с `price_is_per_bed=False` → цена НЕ умножается

Для финансовых endpoint'ов:
- ✅ Нет подтверждённых броней за месяц → `revenue = 0`, `avg_nights = 0`
- ✅ Деление на ноль в `occupancy` при `total_beds = 0` → не краш, возврат `0.0`

---

## Запуск

```bash
# Все тесты модуля
python manage.py test apps.bookings -v 2

# Конкретный класс
python manage.py test apps.bookings.tests.test_services.CreateBookingServiceTests -v 2

# Race-тесты с реальной БД (не SQLite — на SQLite select_for_update noop)
# Убедись, что DB_ENGINE=postgresql в .env перед прогоном
python manage.py test apps.bookings.tests.test_race -v 2
```

**Важно про SQLite:** `select_for_update()` на SQLite — no-op, race-тест пройдёт
ложно-зелёным. Race-тесты прогоняются только на PostgreSQL.
