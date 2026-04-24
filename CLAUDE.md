# CLAUDE.md — Konoq Hostel Backend (konoq-back)

## Роль

Ты — senior Python/Django разработчик. Пишешь production-ready код без лишних комментариев.
Никогда не пиши `# TODO`, `pass`, заглушки или placeholder-логику без явной просьбы.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## Tech Stack

- **Backend**: Django 6.x + Django REST Framework 3.16
- **DB**: PostgreSQL (prod, через `psycopg2-binary`) / SQLite (dev)
- **Auth**: JWT (`djangorestframework-simplejwt` с rotation + blacklist)
- **Docs**: drf-spectacular (OpenAPI 3)
- **Telegram**: aiogram 3 (webhook через async view)
- **WhatsApp**: SendPulse WA Bot API (OAuth2 client_credentials)
- **iCal**: `icalendar` — импорт броней с Booking.com / Airbnb
- **Files**: Pillow для изображений комнат
- **Deploy**: Gunicorn + Docker Compose (PostgreSQL контейнер)

**Нет** (и не добавлять без прямой просьбы): Celery, Redis, DRF ViewSets, pytest, factory_boy.

---

## Структура проекта

```
konoq-back/
├── konoq/                       # Django settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py / asgi.py
├── apps/
│   ├── users/                   # User (manager / admin), JWT
│   ├── rooms/                   # Branch, Room
│   ├── bookings/                # Booking, ICalLink
│   ├── finance/                 # RevenueTarget + aggregations (admin only)
│   ├── tours/                   # Туры (отдельный модуль)
│   ├── tg_bot/                  # Telegram webhook + уведомления владельцу
│   └── wa_bot/                  # WhatsApp webhook + SendPulse + сессии брони
├── docker/
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── requirements.txt
└── .env
```

Текущая организация app (реальная, не ViewSets):

```
apps/<module>/
├── models.py            # модели
├── serializers.py       # DRF serializers
├── views.py             # APIView (логика смешана с HTTP — постепенно выносим)
├── urls.py
├── admin.py
├── signals.py           # где нужно — Django signals
└── migrations/
```

**Целевая архитектура** (для новых модулей и рефакторинга):
- `services.py` — бизнес-логика, всё что `transaction.atomic()`
- `selectors.py` — read-only queryset-функции
- `views.py` — только HTTP, делегирует в services/selectors
- `permissions.py` — кастомные DRF permissions

Не рефакторить старый код "заодно" — только когда явно попросили.

---

## Критические паттерны — ВЫУЧИ НАИЗУСТЬ

### ⛔ Race condition при бронировании → двойная продажа

**Контекст.** `apps/wa_bot/handlers.py::_handle_name` и `apps/bookings/views.py::BookingCreateView`
проверяют вместимость и затем создают `Booking` в несколько запросов. Два клиента
могут одновременно пройти проверку `current_booked + guests <= capacity` и оба забронировать
последнее место.

**НЕПРАВИЛЬНО:**
```python
booked = _get_booked_guests(checkin, checkout, branch_id).get(room_type, 0)
total_capacity = sum(r.capacity for r in rooms_of_type)
if booked + guests > total_capacity:                      # ❌ TOCTOU
    raise ValidationError(...)
Booking.objects.create(...)
```

**ПРАВИЛЬНО** — проверка и insert в одной транзакции с блокировкой комнат:
```python
def create_booking_with_capacity_check(*, branch_id, room_type, checkin, checkout, guests, **data):
    # Guard-проверки ДО atomic
    if checkin >= checkout:
        raise ValidationError(...)
    if guests < 1:
        raise ValidationError(...)

    with transaction.atomic():
        # Блокируем комнаты этого типа → параллельный insert ждёт
        rooms = list(
            Room.objects
                .select_for_update()
                .filter(branch_id=branch_id, room_type=room_type, is_active=True)
        )
        if not rooms:
            raise ValidationError("Нет активных номеров этого типа")

        total_capacity = sum(r.capacity for r in rooms)

        booked = (
            Booking.objects
                .filter(
                    branch_id=branch_id,
                    room=room_type,
                    status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
                    checkin__lt=checkout,
                    checkout__gt=checkin,
                )
                .aggregate(s=Sum("guests"))["s"] or 0
        )
        if booked + guests > total_capacity:
            raise ValidationError("Нет свободных мест")

        return Booking.objects.create(
            branch_id=branch_id, room=room_type,
            checkin=checkin, checkout=checkout, guests=guests,
            **data,
        )
```

Правило: **любое создание/подтверждение брони идёт через сервис с `select_for_update()` на
`Room` этого branch+type ВНУТРИ `transaction.atomic()`.**

---

### ⛔ `select_for_update()` ВСЕГДА внутри `transaction.atomic()`

Без открытой транзакции блокировка снимается немедленно — защиты нет.

**НЕПРАВИЛЬНО:**
```python
room = Room.objects.select_for_update().get(id=id)   # ❌ вне atomic
```

**ПРАВИЛЬНО:**
```python
with transaction.atomic():                            # ✅ atomic ПЕРВЫМ
    room = Room.objects.select_for_update().get(id=id)
```

---

### ⛔ `@atomic` — на сервис, не на view/webhook/handler

**Контекст.** `apps/wa_bot/handlers.py::handle_message` обёрнут в `@atomic`. Проблема:
одна транзакция держится через весь диалог включая I/O (`_send` через SendPulse),
`ValidationError` из вложенного сервиса бросается внутри внешнего `atomic` (→ ломает
принцип "ValidationError до atomic"), и `_send(...)` отправляет сообщение клиенту
ДО commit — если транзакция откатится, клиент получит подтверждение о брони,
которой в БД нет.

**НЕПРАВИЛЬНО:**
```python
@atomic                                              # ❌ на handler'е
def handle_message(phone, text, contact_id=""):
    ...
    b = create_booking_with_capacity_check(...)    # сервис уже атомарен сам
    _send(phone, "Бронь принята!", session)          # ❌ уходит ДО commit
```

**ПРАВИЛЬНО:** `@atomic` живёт на уровне сервиса, где critical section. Handler/view
без декоратора — каждый `session.save()` / create атомарен сам по себе.
```python
def handle_message(phone, text, contact_id=""):    # ✅ без @atomic
    ...
    try:
        b = create_booking_with_capacity_check(...)  # atomic внутри сервиса
    except ValidationError:
        _send(phone, "Нет мест", session)
        return
    _send(phone, "Бронь принята!", session)          # ✅ после commit сервиса
```

Правило: **`@atomic` / `with transaction.atomic()` — только в services.py, никогда
на view, webhook, signal handler или bot message handler.**

---

### ⛔ `ValidationError` — ДО `transaction.atomic()`, не внутри

Бросок `ValidationError` внутри `atomic()` ломает соединение (`needs_rollback=True`).

**НЕПРАВИЛЬНО:**
```python
with transaction.atomic():
    if checkin >= checkout:
        raise ValidationError(...)   # ❌ внутри atomic
```

**ПРАВИЛЬНО:**
```python
if checkin >= checkout:
    raise ValidationError(...)        # ✅ guard до atomic
with transaction.atomic():
    ...
```

---

### ⛔ Внешние API — не через `threading.Thread(daemon=True)`

**Контекст.** `apps/bookings/views.py::_send_tg_notification`,
`apps/wa_bot/handlers.py::_send`, `apps/bookings/signals.py` — все используют daemon threads
для SendPulse/Telegram. **Проблема:** при рестарте Gunicorn / OOM thread умирает, сообщение
теряется, клиент ждёт подтверждение которого не будет. Нет retry, нет очередности.

**НЕПРАВИЛЬНО:**
```python
def _send(phone, text, contact_id):
    threading.Thread(
        target=send_wa_message, args=(phone, text, contact_id), daemon=True,
    ).start()                                       # ❌ fire-and-forget
```

**ПРАВИЛЬНО (текущий минимум — синхронно + таймаут + лог):**
```python
def send_wa_message(phone: str, text: str, contact_id: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("WA send failed phone=%s: %s", phone, exc)
        return None
```
Вызываем синхронно из view — webhook ответит на 200–500 мс позже, это ОК.

**ПРАВИЛЬНО (целевое):** очередь (Celery/RQ) с retry. Добавлять только если явно попросят
— не "улучшать заодно".

---

### ⛔ Уведомления клиенту — только в `post_save`, не в `pre_save`

**Контекст.** `apps/bookings/signals.py::notify_whatsapp_on_confirm` висит на `pre_save`.
Если `save()` упадёт после сигнала — клиент получит "Ваша бронь подтверждена", а в БД
статус останется `pending`.

**ПРАВИЛЬНО:**
```python
@receiver(post_save, sender=Booking)              # ✅ post_save
def notify_whatsapp_on_confirm(sender, instance, created, **kwargs):
    if created:
        return
    # сравнение статуса — через __old_status в __init__ или отдельную модель BookingLog
```

Для сравнения старого/нового статуса — кэшировать в `__init__`:
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.__old_status = self.status
```

---

### ⛔ Fat model: логика в `Booking.save()` → вынести в сервис

**Контекст.** `apps/bookings/models.py::Booking.save()` лезет в `Room`, считает цену,
умножает на `guests`. Это делает `.save()` непредсказуемым (скрытые запросы к БД,
сложно тестировать).

**НЕПРАВИЛЬНО:**
```python
def save(self, *args, **kwargs):
    if not self.pk and (not self.price_per_night or not self.total_price):  # ❌ баг с нулём
        room_obj = Room.objects.filter(room_type=self.room, ...).first()
        if room_obj:
            price = room_obj.price_per_night
            if room_obj.price_is_per_bed:
                price *= self.guests
            ...
    super().save(*args, **kwargs)
```

**ПРАВИЛЬНО** — цена считается в сервисе при создании, `save()` остаётся "тупым":
```python
# apps/bookings/services.py
def calculate_booking_price(*, room: Room, guests: int, nights: int) -> tuple[Decimal, Decimal]:
    per_night = room.price_per_night * guests if room.price_is_per_bed else room.price_per_night
    total = per_night * Decimal(max(nights, 0))
    return per_night, total

def create_booking(*, room: Room, guests: int, checkin, checkout, **data) -> Booking:
    nights = (checkout - checkin).days
    per_night, total = calculate_booking_price(room=room, guests=guests, nights=nights)
    return Booking.objects.create(
        room=room.room_type, branch_id=room.branch_id,
        guests=guests, checkin=checkin, checkout=checkout,
        price_per_night=per_night, total_price=total,
        **data,
    )
```

---

### ⛔ Баг с нулём: `if not price` → `if price is None`

```python
# НЕПРАВИЛЬНО
if not self.price_per_night:                 # ❌ 0 = False → условие сработает
    self.price_per_night = calculated

# ПРАВИЛЬНО
if self.price_per_night is None:             # ✅ 0 — валидное значение
    self.price_per_night = calculated
```

Применимо ко всем денежным/количественным полям: `price_per_night`, `total_price`,
`price_is_per_bed`, `guests`, `capacity`.

---

### ⛔ Агрегация — в БД, не в Python

**Контекст.** `apps/finance/views.py` делает группировку в цикле вместо SQL:
```python
# НЕПРАВИЛЬНО (из текущего кода)
by_source = {}
for b in qs:                                              # ❌ Python-цикл
    by_source[b.source] = {...}
    by_source[b.source]["revenue"] += b.total_price

total_n = sum((b.checkout - b.checkin).days for b in base_qs)  # ❌ table scan

guest_nights = sum(b.guests * min(...) for b in bookings)      # ❌
```

**ПРАВИЛЬНО:**
```python
by_source = (
    qs.values("source")
      .annotate(count=Count("id"), revenue=Sum("total_price"))
      .order_by("-revenue")
)

avg = qs.annotate(
    nights=ExpressionWrapper(
        F("checkout") - F("checkin"), output_field=DurationField(),
    )
).aggregate(avg_nights=Avg("nights"))
```

Правило: **любой `for x in queryset` где накапливаются суммы — это баг.**

---

### ⛔ Роль admin — через permission-класс, не `_is_admin(user)` в каждом view

**Контекст.** `apps/finance/views.py` дублирует `if not _is_admin(request.user): return 403`
в каждом методе.

**ПРАВИЛЬНО** — один permission-класс:
```python
# apps/users/permissions.py
from rest_framework.permissions import BasePermission
from apps.users.models import User

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )

# apps/finance/views.py
class FinanceSummaryView(APIView):
    permission_classes = [IsAdmin]                 # ✅ один декларативный класс
```

---

### ⛔ Webhook без проверки источника и идемпотентности

**Контекст.** `apps/wa_bot/views.py::WhatsAppWebhookView` принимает любой POST.
SendPulse не подписывает запросы, но IP-allowlist возможен. Плюс при retry — дубль
сообщения → дубль брони.

**Правила:**
- Каждое `event` от SendPulse имеет `id` (или составной ключ `message.id + contact.id`).
  Хранить их в таблице `WhatsAppProcessedEvent(event_id unique, processed_at)` и
  пропускать повторные.
- `urllib.request.urlopen(..., timeout=10)` — всегда с таймаутом.
- Если появится HMAC от SendPulse — проверять до парсинга body.

---

### ⛔ Кросс-модульный импорт приватных функций из views

```python
# НЕПРАВИЛЬНО — в apps/wa_bot/handlers.py
from apps.rooms.views import _get_booked_guests         # ❌ приватная из views
from apps.bookings.views import _send_tg_notification   # ❌ приватная из views
```

**ПРАВИЛЬНО** — общая логика живёт в `selectors.py` / `services.py`:
```python
# apps/bookings/selectors.py
def get_booked_guests_by_type(*, checkin, checkout, branch_id=None) -> dict:
    ...

# apps/wa_bot/handlers.py
from apps.bookings.selectors import get_booked_guests_by_type
```

---

### ⛔ Пагинация — на всех list-эндпоинтах

**Контекст.** `BookingListView`, `BranchListView`, `RoomListView`, `RevenueTargetView`
возвращают все записи без пагинации.

Включить в `settings.py`:
```python
REST_FRAMEWORK = {
    ...
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
```
И использовать `generics.ListAPIView` / `get_paginated_response` где list. Существующие
`APIView.get()` возвращающие голый массив — не ломать, но для новых endpoint использовать
пагинацию сразу.

---

## Ключевые модели и правила

### Booking (`apps/bookings/models.py`)
- `status`: `pending → confirmed → cancelled` (обратно не идёт без явного сервиса)
- `nights = (checkout - checkin).days` — property
- Источники: `direct`, `booking_com`, `airbnb`, `walk_in`, `telegram`, `whatsapp`
- Цена считается в сервисе при создании, не в `save()` (см. антипаттерн выше)
- Проверка доступности: единственная правда — `apps/bookings/selectors.py`
  (после рефакторинга; сейчас в `apps/rooms/views.py::_get_booked_guests`)
- Пересечение дат: `checkin__lt=other.checkout AND checkout__gt=other.checkin`

### Room (`apps/rooms/models.py`)
- `price_is_per_bed=True` для дормов → итоговая цена = `price * guests`
- `capacity` — вместимость (для дорма = число шконок)
- Удаление Branch каскадно удаляет Rooms (`CASCADE`), но Booking.branch — `SET_NULL`
  → после удаления филиала история броней остаётся без привязки

### ICalLink (`apps/bookings/models.py`)
- unique_together: `(branch, room_type, source)` — одна ссылка на комбинацию
- Синхронизация: `last_synced_at` обновляется командой `python manage.py ...`
  (смотри `apps/bookings/management/`)
- Импортированные брони: `source = BOOKING_COM | AIRBNB`, `status = CONFIRMED`

### User (`apps/users/models.py`)
- Роли: `manager`, `admin`
- Финансы (`apps/finance/`) — только `admin` через `IsAdmin` permission

### WhatsAppSession (`apps/wa_bot/models.py`)
- `unique=True` по `phone` → одна активная сессия на номер
- Сессия истекает через 3 часа бездействия (проверка в handler)
- `data` — JSON с контекстом (branch_id, checkin, rooms_map, contact_id)

---

## API соглашения

- Base URL: `/api/<module>/` (без версионирования пока — не добавлять)
- Swagger: `/api/docs/`, schema: `/api/schema/`
- Формат ошибок — стандартный DRF (`{"detail": "..."}` или `{"field": ["msg"]}`)
- Все endpoints документируются `@extend_schema(tags=[...], summary=...)`
- Публичные endpoints (`AllowAny`): `BookingCreateView`, `BranchListView.get`,
  `RoomListView.get` — всё остальное `IsAuthenticated`

---

## Интеграции — правила

### SendPulse (WhatsApp)
- OAuth2 token кэшируется в модуле (`_token_cache`) — не thread-safe, но приемлемо
  для одного воркера. При росте → Redis.
- Все `urlopen(...)` → с `timeout=10`
- Ошибки не пробрасывать наружу — логировать и возвращать `None`
- `contact_id` **обязателен** для `send_wa_message` — без него SendPulse отвергает

### Telegram (aiogram)
- Webhook: `/api/tg/` — async view
- Уведомления владельцу — синхронно через `asyncio.run(...)` в вызове, не через thread
- `TG_OWNER_ID` в `.env` — единственный получатель уведомлений

### iCal
- Парсинг — `icalendar.Calendar.from_ical(...)`
- Команда синхронизации в `apps/bookings/management/commands/` — запускать через cron
  (Celery пока нет)
- Идемпотентность: `Booking.objects.update_or_create(external_uid=..., defaults={...})`

---

## Запрещено

- `threading.Thread(daemon=True)` для внешних API (SendPulse, Telegram) без явного согласования
- `@atomic` / `with transaction.atomic()` на view, webhook-handler, signal или bot message handler — только в services
- `select_for_update()` вне `transaction.atomic()`
- `ValidationError` / `ServiceError` внутри `transaction.atomic()` — только до `atomic`
- Агрегация/группировка в Python вместо SQL (`annotate`, `aggregate`, `values`)
- `if not price` вместо `if price is None` — баг с нулём
- Логика в `save()` модели (запросы к БД, цепочки вычислений) — только в services
- Кросс-модульный импорт `_private_func` из views другого app — только из services/selectors
- Уведомление клиенту в `pre_save` — только в `post_save` с проверкой старого статуса
- Проверка роли строкой (`user.role == "admin"`) в каждом view — только через permission-класс
- `Booking.objects.all()` без фильтра и пагинации на защищённых endpoint'ах
- `urlopen(...)` без `timeout`
- Создание Booking напрямую в handler-е WA-бота без проверки вместимости в `atomic`
- Хардкод `"admin"`, `"confirmed"` и т.д. — только через `TextChoices`
- `print()` — только `logger`
