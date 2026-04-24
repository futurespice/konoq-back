# Code Review

Сделай code review файла/модуля `$ARGUMENTS` строго по правилам CLAUDE.md.

## Проверяй в таком порядке:

### 🔴 Критические (блокируют merge)

- [ ] **Race condition при бронировании** — проверка вместимости и `Booking.objects.create()`
      без `select_for_update()` на `Room` внутри общего `transaction.atomic()`. Ищи в
      `apps/wa_bot/handlers.py`, `apps/bookings/views.py`, `apps/bookings/signals.py`.
- [ ] **`select_for_update()` вне `transaction.atomic()`** — блокировка снимается сразу,
      защиты нет.
- [ ] **`ValidationError` внутри `transaction.atomic()`** — транзакция уходит в
      `needs_rollback=True`, ломает соединение.
- [ ] **`threading.Thread(daemon=True)` для внешних API** (SendPulse, Telegram) —
      теряется при рестарте Gunicorn. Должно быть синхронно с `timeout` или в очереди.
- [ ] **Уведомление клиента в `pre_save` signal** — может отправиться до того как
      `save()` пройдёт. Только `post_save`.
- [ ] **Логика в `Booking.save()`** — запросы к `Room`, расчёт цены. Выносить в services.
- [ ] **Баг с нулём**: `if not price` вместо `if price is None` — price=0 валидно.
- [ ] **Агрегация/группировка в Python** вместо `annotate`/`aggregate` — OOM на проде.
      Типичное: `for b in qs: totals[key] += b.total_price` → в
      `qs.values(key).annotate(Sum(...))`.
- [ ] **`user.role == "admin"` строкой в каждом view** вместо permission-класса `IsAdmin`.
- [ ] **Webhook `WhatsAppWebhookView`** без проверки идемпотентности (повтор событий от
      SendPulse → дубль брони).
- [ ] **`urlopen(...)` без `timeout`** — висит навсегда при недоступности API.
- [ ] **`Booking.objects.all()` без фильтра** на защищённом endpoint.
- [ ] **Финансовые endpoints** без `IsAdmin` — доступны любому `IsAuthenticated`.
- [ ] **Прямая запись в модель другого app** (например, `wa_bot` пишет в `Booking` в
      обход сервиса `bookings`).

### 🟡 Важные (нужно исправить)

- [ ] `if value` вместо `if value is not None` для числовых полей (`guests`, `capacity`,
      `price_per_night`, `total_price`, `nights`).
- [ ] Отсутствует `transaction.atomic()` при нескольких write-операциях.
- [ ] N+1 запросы — нет `select_related`/`prefetch_related` (типично: обращение к
      `booking.branch.name` в цикле).
- [ ] Кросс-модульный импорт `_private_func` из `views.py` другого app
      (`from apps.rooms.views import _get_booked_guests` и т.п.) — выносить в
      `selectors.py` / `services.py`.
- [ ] Не keyword-only аргументы в services (`def f(a, b)` вместо `def f(*, a, b)`).
- [ ] Отсутствует `@extend_schema` на view.
- [ ] Один serializer для input и output.
- [ ] Хардкод строк вместо `TextChoices` (`"admin"`, `"confirmed"`, `"whatsapp"`).
- [ ] Отсутствует пагинация на list-endpoints (`BookingListView`, `RoomListView` и т.д.).
- [ ] Нет фильтрации `status__in=[CONFIRMED, PENDING]` при проверке доступности —
      учитываем только активные брони, не отменённые.
- [ ] `print()` вместо `logger = logging.getLogger(__name__)`.
- [ ] Пересечение дат через `checkin >= other.checkout` вместо
      `checkin__lt=other.checkout AND checkout__gt=other.checkin`.
- [ ] Итерация `for event_data in events:` без защиты от дубля — нужна таблица
      processed events.

### 🟢 Замечания (желательно)

- [ ] Нет type annotations у аргументов service-функций.
- [ ] Неиспользуемые импорты.
- [ ] Тесты не покрывают edge cases (заезд=выезд, guests=0, дорм с `price_is_per_bed`).
- [ ] Нет docstring на сложных service-функциях.
- [ ] Миграция не создана после изменения модели.
- [ ] `MONTH_NAMES_RU` в `finance/views.py` можно вынести в constants.

## Эталонные паттерны из CLAUDE.md

### Бронирование без race condition:
```python
def create_booking_with_capacity_check(*, branch_id, room_type, checkin, checkout, guests, **data):
    if checkin >= checkout:
        raise ValidationError(...)

    with transaction.atomic():
        rooms = list(
            Room.objects
                .select_for_update()
                .filter(branch_id=branch_id, room_type=room_type, is_active=True)
        )
        total_capacity = sum(r.capacity for r in rooms)
        booked = Booking.objects.filter(
            branch_id=branch_id, room=room_type,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
            checkin__lt=checkout, checkout__gt=checkin,
        ).aggregate(s=Sum("guests"))["s"] or 0

        if booked + guests > total_capacity:
            raise ValidationError("Нет свободных мест")
        return Booking.objects.create(...)
```

### Permission вместо строки:
```python
class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )

class FinanceSummaryView(APIView):
    permission_classes = [IsAdmin]
```

### Агрегация в БД:
```python
by_source = (
    qs.values("source")
      .annotate(count=Count("id"), revenue=Sum("total_price"))
      .order_by("-revenue")
)
```

### Внешний API синхронно с таймаутом:
```python
def send_wa_message(phone, text, contact_id, timeout=10):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("WA send failed phone=%s: %s", phone, exc)
        return None
```

## Формат ответа

Для каждой проблемы:
```
[УРОВЕНЬ] apps/module/file.py:строка
Проблема: что не так
Исправление: конкретный код как должно быть
```

В конце — таблица findings по уровням и итог: **APPROVE** / **REQUEST_CHANGES**.
Если одна и та же ошибка встречается в нескольких местах — выдели отдельным блоком
"Системные паттерны".
