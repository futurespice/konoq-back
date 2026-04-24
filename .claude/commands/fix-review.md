# Исправить findings из code review

Исправь все найденные проблемы в `$ARGUMENTS` строго по правилам CLAUDE.md.

## Алгоритм:

1. Прочитай `CLAUDE.md` — особенно раздел "Критические паттерны".
2. Прочитай файл(ы) из `$ARGUMENTS`.
3. Исправь каждую проблему по чеклисту ниже.
4. После исправлений запусти `/review $ARGUMENTS` для проверки — должен вернуть **APPROVE**.

**Surgical Changes:** трогаем только те строки, которые относятся к findings. Не
переформатируем, не улучшаем соседний код, не меняем стиль "заодно".

## Чеклист исправлений:

### Race condition при бронировании
Найди каждое создание `Booking` после проверки вместимости.
Оберни в `transaction.atomic()` + `Room.objects.select_for_update()`:
```python
with transaction.atomic():
    rooms = list(
        Room.objects.select_for_update()
            .filter(branch_id=branch_id, room_type=room_type, is_active=True)
    )
    booked = Booking.objects.filter(
        branch_id=branch_id, room=room_type,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
        checkin__lt=checkout, checkout__gt=checkin,
    ).aggregate(s=Sum("guests"))["s"] or 0
    total = sum(r.capacity for r in rooms)
    if booked + guests > total:
        raise ValidationError("Нет свободных мест")
    booking = Booking.objects.create(...)
```

### `select_for_update()` вне `atomic()`
Найди каждый `select_for_update()`. Если над ним нет `with transaction.atomic():` —
добавь ПЕРВЫМ.

### `ValidationError` внутри `atomic()`
Найди все `raise ValidationError` / `raise ServiceError` внутри `with transaction.atomic():`.
Вынеси guard-проверки ДО открытия транзакции.

### `threading.Thread(daemon=True)` для внешних API
Найди `threading.Thread(target=send_wa_message, ..., daemon=True).start()` и
`threading.Thread(target=notify_owner_new_booking, ..., daemon=True).start()`.
Замени на синхронный вызов с таймаутом:
```python
# apps/wa_bot/sendpulse_api.py
def send_wa_message(phone, text, contact_id, timeout=10):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("WA send failed phone=%s: %s", phone, exc)
        return None
```
Вызов — синхронно из view/handler. Webhook ответит на 200–500 мс позже — это ОК.

### Уведомление в `pre_save` → `post_save`
В `apps/bookings/signals.py` замени `@receiver(pre_save, ...)` на `@receiver(post_save, ...)`.
Для сравнения старого/нового статуса — через `__old_status` в `Booking.__init__`:
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.__old_status = self.status
```

### Логика в `Booking.save()`
Вынеси расчёт цены из `save()` в `apps/bookings/services.py::calculate_booking_price(...)`.
`Booking.save()` оставь "тупым" — только `super().save(*args, **kwargs)`.
Цена проставляется в сервисе ДО `create()`.

### Баг с нулём
Найди `if not price`, `if not total_price`, `if not guests` и т.д. Замени на
`if X is None`:
```python
if self.price_per_night is None:     # ← вместо if not self.price_per_night
    self.price_per_night = calculated
```

### Агрегация в Python-цикле
Найди любой `for obj in queryset:` где накапливаются суммы/счётчики.
Замени на `queryset.values("key").annotate(count=Count("id"), total=Sum("field"))`.

Конкретные места в `apps/finance/views.py`:
- `BySourceView.get()` — цикл `for b in qs: by_source[...] += b.total_price` →
  `qs.values("source").annotate(count=Count("id"), revenue=Sum("total_price"))`
- `ByBranchView.get()` — аналогично по `branch_id`
- `FinanceSummaryView.get()` — `sum((b.checkout - b.checkin).days for b in base_qs)` →
  через `annotate(nights=ExpressionWrapper(F("checkout") - F("checkin"), ...))` + `Avg`
- `OccupancyView.get()` — `sum(b.guests * min(...))` → через SQL с `LEAST`/`GREATEST`

### Проверка роли `_is_admin(user)`
Создай `apps/users/permissions.py::IsAdmin` (см. CLAUDE.md).
В `apps/finance/views.py` удали все `if not _is_admin(request.user): return 403` и
поставь `permission_classes = [IsAdmin]`.
Удали саму функцию `_is_admin` после того как все её вызовы ушли.

### Webhook без идемпотентности
В `apps/wa_bot/` создай модель:
```python
class WhatsAppProcessedEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    processed_at = models.DateTimeField(auto_now_add=True)
```
В `WhatsAppWebhookView.post` — перед `handle_message` делай
`get_or_create(event_id=...)`, если `created=False` → пропускаем.

### `urlopen` без `timeout`
Во всех `urllib.request.urlopen(req)` в `apps/wa_bot/sendpulse_api.py` добавь
`timeout=10`.

### Кросс-модульный импорт `_private` из views
Найди `from apps.<module>.views import _private_func`. Перенеси функцию в
`apps/<module>/selectors.py` (для read) или `services.py` (для write).
Импорт обнови:
```python
# Было
from apps.rooms.views import _get_booked_guests
# Стало
from apps.bookings.selectors import get_booked_guests_by_type
```

### Пагинация
Для новых list-endpoint'ов — `generics.ListAPIView` с `PageNumberPagination` и
`PAGE_SIZE=20`. Существующие `APIView` не трогаем (не ломаем фронт) — только упоминаем
в findings.

### Нетипизированные аргументы
Добавь type annotations всем аргументам service-функций.

## После исправлений:
```
/review $ARGUMENTS
```
Должен вернуть **APPROVE**. Если нет — итерация.
