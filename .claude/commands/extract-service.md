# Вынести логику из views.py в services/selectors

Рефакторинг: переводим модуль на целевую архитектуру (`services.py` + `selectors.py`)
без ломки существующих эндпоинтов и фронта.

## Формат `$ARGUMENTS`:
- `apps/<module>` — весь модуль
- `apps/<module>/views.py::<ClassName>` — конкретный view

Примеры:
- `apps/finance` — вынести агрегации из `finance/views.py` в `finance/selectors.py`
- `apps/bookings/views.py::BookingListView` — только один view

## Философия

**Surgical Changes:** существующие URL, request/response схемы, serializers — не
трогаем. Меняется только *куда* уехала логика. Фронт ничего не должен заметить.

## Правила разделения

Что куда переезжает:

| Код в `views.py` | Куда |
|---|---|
| `Model.objects.filter(...).select_related(...)` с нетривиальной логикой | `selectors.py` |
| Агрегации (`values().annotate()`, `aggregate()`) | `selectors.py` |
| Цикл по QuerySet для сбора данных | переписать в `selectors.py` через SQL |
| `Model.objects.create(...)`, `.save()`, `.delete()` | `services.py` |
| `transaction.atomic()` блоки | `services.py` |
| Проверки бизнес-правил (`if ... raise ValidationError`) | `services.py` (guard-ы ДО atomic) |
| Вызовы внешних API (SendPulse, Telegram) | `services.py` |
| Отправка signals / уведомления после create | `services.py` |
| `request.query_params.get("...")` парсинг | остаётся в view |
| `serializer.is_valid(raise_exception=True)` | остаётся в view |
| `permission_classes` | остаётся в view |
| `@extend_schema` | остаётся в view |

## План (Goal-Driven):

```
1. Прочитать текущий views.py → verify: понимаю где логика, где HTTP
2. Создать selectors.py с чистыми read-функциями → verify: нет импортов django.db.transaction
3. Создать services.py с write-функциями → verify: все atomic-блоки тут
4. Переписать view: только парсинг params + вызов selector/service + Response →
   verify: view стал короче, логика не дублируется
5. Прогнать существующие тесты → verify: всё зелёное
6. Запустить /review apps/<module> → verify: APPROVE
```

## Шаблоны

### `selectors.py`

Для каждой функции:
- keyword-only аргументы (`*,`)
- возвращает `QuerySet` или `dict` (не `list(qs)` — пагинация снаружи)
- никакого `transaction.atomic`, никакого `.save()`
- `select_related` / `prefetch_related` — для FK, используемых далее

```python
# apps/bookings/selectors.py
from datetime import date
from django.db.models import Q, QuerySet, Sum
from .models import Booking


def list_bookings(
    *,
    status: str | None = None,
    source: str | None = None,
    branch_id: int | None = None,
    search: str | None = None,
    checkin_from: date | None = None,
) -> QuerySet[Booking]:
    qs = Booking.objects.select_related("branch")
    if status:
        qs = qs.filter(status=status)
    if source:
        qs = qs.filter(source=source)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(surname__icontains=search)
            | Q(phone__icontains=search) | Q(country__icontains=search)
        )
    if checkin_from:
        qs = qs.filter(checkin__gte=checkin_from)
    return qs


def get_booking_stats(*, branch_id: int | None = None) -> dict:
    qs = Booking.objects.all()
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        confirmed=Count("id", filter=Q(status=Booking.Status.CONFIRMED)),
        cancelled=Count("id", filter=Q(status=Booking.Status.CANCELLED)),
    )
```

### `services.py`

```python
# apps/bookings/services.py
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Booking


def update_booking_status(*, booking_id: int, new_status: str) -> Booking:
    # Guard-проверки ДО atomic
    allowed = {
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
        Booking.Status.CANCELLED,
    }
    if new_status not in allowed:
        raise ValidationError(f"Недопустимый статус: {new_status}")

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(id=booking_id)
        booking.status = new_status
        booking.save(update_fields=["status", "updated_at"])
    return booking


def delete_booking(*, booking_id: int) -> None:
    Booking.objects.filter(id=booking_id).delete()
```

### `views.py` после рефакторинга

```python
# apps/bookings/views.py
class BookingListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["bookings"], summary="Список бронирований", ...)
    def get(self, request):
        qs = list_bookings(
            status=request.query_params.get("status"),
            source=request.query_params.get("source"),
            branch_id=request.query_params.get("branch"),
            search=request.query_params.get("search"),
            checkin_from=request.query_params.get("checkin"),
        )
        return Response(BookingListSerializer(qs, many=True).data)


class BookingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["bookings"], summary="Обновить статус", ...)
    def patch(self, request, pk):
        serializer = BookingStatusUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            booking = update_booking_status(
                booking_id=pk,
                new_status=serializer.validated_data["status"],
            )
        except Booking.DoesNotExist:
            return Response({"detail": "Не найдено."}, status=404)
        return Response(BookingListSerializer(booking).data)
```

## Что **НЕ** делаем в этом рефакторинге

- ❌ Не меняем URL-схему
- ❌ Не переименовываем endpoint'ы
- ❌ Не переделываем serializers
- ❌ Не меняем shape ответа API (фронт не должен ничего заметить)
- ❌ Не добавляем пагинацию, если её не было (это отдельная задача)
- ❌ Не исправляем "заодно" баги, которые не относятся к текущему файлу — только
  упоминаем в финальном отчёте

## После рефакторинга

1. Прогнать тесты: `python manage.py test apps.<module>`
2. Запустить `/review apps/<module>` — должен вернуть **APPROVE**
3. Ручная проверка: Swagger `/api/docs/` открывается, примеры запросов работают
4. Вывести краткий отчёт:
   - Что переехало в `selectors.py` (список функций)
   - Что переехало в `services.py` (список функций)
   - Сколько строк стало во `views.py` до/после
   - Замеченные, но **не исправленные** баги (для отдельной задачи)
