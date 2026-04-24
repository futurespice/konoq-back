# Bed-level Booking — Спецификация

**Статус:** черновик, ждёт утверждения
**Цель:** заменить бронирование "по типу комнаты" на бронирование конкретных шконок
(`Bed`), чтобы поддерживать группы до 20 человек, "забрать комнату целиком" и
точный учёт доступности без race conditions на уровне агрегата.

---

## 1. Продуктовая модель

### Что есть сейчас
- `Booking` хранит `room` (TextChoices: `dorm_4`, `single`, ...) и `guests` (число)
- Доступность считается как `Σ guests по активным броням этого типа < Σ capacity комнат этого типа` в филиале
- Нельзя забронировать конкретную шконку, нельзя смешать типы в одной брони,
  группу > 8 приходится отказывать либо разруливать руками

### Что должно стать
- Бронь = одна `Booking` + N привязок к конкретным шконкам (`BookingBed`)
- Группа из 10 человек → одна `Booking`, 10 `BookingBed`
- "Пара в двухместной комнате" → одна `Booking`, 2 `BookingBed` в одной `Room`
- "Дорм-4 целиком одной семье" → одна `Booking`, 4 `BookingBed` в одной `Room`,
  цена = `4 × price_per_bed × nights`
- Смешанное: часть в дорм-4, часть в дорм-6 → одна `Booking`, шконки из разных `Room`

### Цены (согласовано)
- **Дорм-комнаты** (`price_is_per_bed = True`): цена за шконку/ночь задана на
  уровне `Room`. У разных дорм-4 могут быть разные цены. Итог =
  `Σ по шконкам брони (price_per_bed комнаты этой шконки) × nights`
- **Приватные комнаты** (`price_is_per_bed = False`, single / double-together / ...):
  цена за комнату/ночь на уровне `Room`. Итог = `price_per_night × nights`.
  "Забрать дорм-4 целиком" ≠ это: в дорме всё равно считаем поштучно за шконки.

---

## 2. Модель данных

### 2.1 Новые таблицы

```python
# apps/rooms/models.py
class Bed(models.Model):
    """
    Конкретная шконка/кровать внутри Room.

    Для приватных комнат (single, double_together, double_separate) создаётся
    столько Bed сколько capacity у Room — но бронируется "вся комната" как
    один набор шконок через флаг Booking.is_private_booking (см. services).
    """
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.CASCADE,
        related_name="beds",
    )
    label = models.CharField(
        max_length=20,
        help_text="Идентификатор шконки внутри комнаты: '1', '2', 'нижняя', 'у окна'",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("room", "label")
        ordering = ["room", "label"]

    def __str__(self):
        return f"{self.room} / {self.label}"
```

```python
# apps/bookings/models.py
class BookingBed(models.Model):
    """
    Привязка брони к конкретной шконке.

    checkin/checkout денормализованы (копия из Booking) для индексного
    поиска пересечений без JOIN.
    """
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="beds",
    )
    bed = models.ForeignKey(
        "rooms.Bed",
        on_delete=models.PROTECT,   # шконку с активными бронями нельзя удалить
        related_name="bookings",
    )
    checkin = models.DateField()
    checkout = models.DateField()
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    # snapshot цены комнаты на момент брони — чтобы исторические данные
    # не поехали при смене тарифов

    class Meta:
        indexes = [
            # Главный индекс для проверки пересечений по шконке
            models.Index(fields=["bed", "checkin", "checkout"]),
            # Для фильтрации активных броней
            models.Index(fields=["checkin", "checkout"]),
        ]
        # Нельзя забронировать одну шконку дважды на тот же день —
        # но constraint на диапазоны в Django неудобен, проверяем в сервисе
```

### 2.2 Изменения в существующих моделях

```python
class Booking(models.Model):
    # УДАЛИТЬ: room (CharField choices) — шконки в BookingBed
    # УДАЛИТЬ: price_per_night, total_price — считаются из BookingBed.aggregate(Sum)
    #    (либо оставить как snapshot для исторических, решить на этапе 1)
    # guests остаётся — для валидации "число BookingBed == guests"
    # branch остаётся — для быстрой фильтрации и iCal по филиалу

    is_private_booking = models.BooleanField(
        default=False,
        help_text="Группа забронировала комнату целиком — остальные не подсаживаются",
    )
    # ↑ нужно для дорма: если is_private_booking=True и гостей<capacity,
    # система НЕ подсаживает чужих на оставшиеся шконки
```

### 2.3 Что удаляется

- `apps/bookings/selectors.py::get_booked_guests_by_type` — больше не нужна
  (заменяется на `get_available_beds`)
- `Booking.room` (CharField) — после миграции данных

---

## 3. Миграция данных

### 3.1 Генерация Bed из существующих Room
Для каждой `Room` создать `capacity` штук `Bed` с label `"1"`, `"2"`, ...

```python
# data-migration внутри новой миграции rooms
for room in Room.objects.all():
    for i in range(1, room.capacity + 1):
        Bed.objects.get_or_create(room=room, label=str(i))
```

### 3.2 BookingBed для исторических Booking
Для каждой существующей `Booking`:
1. Найти `Room` того же `branch_id` и `room_type` (совпадение по старому `Booking.room`)
2. Найти `guests` свободных шконок среди этих `Room` на даты `checkin..checkout`
3. Создать `BookingBed` на каждую найденную шконку
4. Если не нашлось достаточно шконок (легаси-пересечения) — создать `BookingBed` без
   проверки пересечений, но с флагом в `Booking.comment += " [legacy_bed_assigned]"`.
   Это ок для прошедших дат.

**Edge case:** если `Booking.room` не совпадает ни с одной `Room.room_type` в
филиале (например, тип `family` в `Booking.RoomType` которого нет в
`Room.RoomType`) — помечаем бронь как `status=cancelled` с комментарием
`[legacy_no_matching_room]` и не создаём `BookingBed`. Админ разберёт.

### 3.3 Порядок миграций
```
rooms/migrations/0005_bed.py              — создать таблицу Bed + datamigration генерации
bookings/migrations/0003_bookingbed.py    — создать BookingBed + datamigration привязки
bookings/migrations/0004_is_private.py    — добавить Booking.is_private_booking
bookings/migrations/0005_drop_room.py     — УДАЛИТЬ Booking.room (ПОСЛЕ переключения кода)
```

Миграция `0005_drop_room` накатывается **только после Этапа 3** (когда весь код
перестал читать `Booking.room`).

---

## 4. Сервисы

### 4.1 `get_available_beds` (selector)

```python
def get_available_beds(
    *,
    branch_id: int,
    checkin: date,
    checkout: date,
    room_type: str | None = None,
) -> QuerySet[Bed]:
    """
    Шконки которые свободны на период checkin..checkout в филиале.
    Опциональный фильтр по типу комнаты.

    Учитывает:
    - пересечение через BookingBed (status in pending|confirmed)
    - is_private_booking: если на этой Room есть активная private-бронь,
      ВСЕ шконки этой Room считаются недоступными даже если часть формально свободна
    - is_active: Bed и Room должны быть активны
    """
```

### 4.2 `auto_assign_beds` (service)

```python
def auto_assign_beds(
    *,
    branch_id: int,
    room_type: str,
    checkin: date,
    checkout: date,
    guests: int,
    want_private_room: bool = False,
) -> list[Bed]:
    """
    Автоподбор шконок под запрос.

    Алгоритм:
    1. Взять свободные Bed этого room_type в филиале.
    2. Сгруппировать по Room: {room_id: [bed1, bed2, ...]}
    3. Если want_private_room:
       - Найти Room где ВСЕ шконки свободны И len(beds) >= guests
       - Если есть несколько — выбрать с минимальной capacity >= guests
         (не тратим дорм-8 на пару)
       - Вернуть первые `guests` шконок этой Room
       - Если не нашлось — ValidationError("Нет свободных комнат целиком")

    4. Если НЕ want_private_room (обычный подбор):
       - Отсортировать Room по числу свободных шконок (по убыванию), чтобы
         не дробить группу по нескольким комнатам без нужды
       - Жадно набирать шконки: сначала все из первой Room, потом из следующей
       - Если набралось >= guests → вернуть первые `guests`
       - Иначе → ValidationError("Нет свободных мест на эти даты")
    """
```

**Сортировка "минимум дробления":** группа из 3 в филиале где свободно
`{дорм-4: 2 шконки, дорм-6: 6 шконок}` должна получить 3 шконки в дорм-6
(там все вместе), а не 2+1. Это оптимизация UX, не обязательна на этапе 2 —
можно добавить позже.

### 4.3 `create_booking_with_beds` (service)

```python
def create_booking_with_beds(
    *,
    branch_id: int,
    beds: list[Bed],
    checkin: date,
    checkout: date,
    is_private_booking: bool,
    name: str, surname: str = "", phone: str,
    source: str, **extra_fields,
) -> Booking:
    """
    Создать бронь на конкретный список шконок.

    Guard-проверки ДО atomic:
    - checkin < checkout
    - checkin >= today (для source != ICAL)
    - len(beds) == len(set(beds)) — без дублей
    - len(beds) >= 1

    Внутри atomic:
    - SELECT FOR UPDATE на всех Bed из списка
    - Проверка что ни одна шконка не пересекается с активной BookingBed
    - Проверка что если is_private_booking — ни одна другая бронь не делит
      Room этих шконок
    - Создать Booking
    - Создать BookingBed × N с snapshot цены Room.price_per_night

    Цена брони считается из BookingBed:
    - Дорм: Σ (bed.room.price_per_night × nights) по всем beds
    - Приватная (single/double_together/double_separate): цена Room × nights
      (не умножается на число шконок)
    """
```

### 4.4 `calculate_booking_total` (helper)

```python
def calculate_booking_total(beds: list[Bed], nights: int) -> Decimal:
    """
    Дорм-режим: Σ(bed.room.price_per_night) × nights
    Приватная комната: price_per_night комнаты × nights (не × на число шконок)

    Определяется по Room.price_is_per_bed первой шконки.
    Гарантия контракта: все beds в одной брони — одного price_is_per_bed
    (проверяется при создании; на уровне модели это инвариант).
    """
```

---

## 5. API

### 5.1 Новые endpoints

#### `GET /api/availability/`
Показывает свободные шконки и комнаты.
```
?branch=1&checkin=2026-05-10&checkout=2026-05-14&room_type=dorm_4&guests=3

Ответ:
{
  "room_type": "dorm_4",
  "total_free_beds": 7,
  "options": [
    {
      "room_id": 12, "room_number": "101",
      "free_beds": 4, "beds": [{"id":45,"label":"1"}, ...],
      "price_per_bed_night": 500,
      "can_take_whole_room": true,
      "whole_room_price": 500 * 4 * nights
    },
    ...
  ]
}
```

#### `POST /api/bookings/preview/`
Автоподбор без создания брони — возвращает "вот что система подберёт".
```
Вход: {branch, room_type, checkin, checkout, guests, want_private_room}
Ответ: {
  "beds": [{"id":45,"room":"101","label":"1"}, ...],
  "total_price": 6000,
  "nights": 3,
  "can_confirm": true
}
Или 400 ValidationError если не подобралось.
```

#### `POST /api/bookings/`  (обновлённый)
Два режима:
```
Режим A (автоподбор): {branch, room_type, checkin, checkout, guests, ...guest_data}
  → сервер вызывает auto_assign_beds + create_booking_with_beds

Режим B (явный выбор): {branch, bed_ids: [45, 46, 47], checkin, checkout, ...guest_data}
  → сервер вызывает create_booking_with_beds напрямую
```

### 5.2 Ответ Booking теперь включает шконки
```json
{
  "id": 42, "status": "pending",
  "checkin": "...", "checkout": "...", "guests": 4,
  "beds": [
    {"room_number": "101", "label": "1", "room_type": "dorm_4"},
    {"room_number": "101", "label": "2", "room_type": "dorm_4"},
    ...
  ],
  "is_private_booking": true,
  "total_price": 6000
}
```

---

## 6. Новый WA-флоу

Текущий: `язык → филиал → даты → гостей → тип → имя → создание`

Новый:
```
язык → филиал → даты → гостей → тип
       ↓
       [автоподбор]
       ↓
"Подобрали: комната №101, шконки 1-4. Цена: 6000 сом за 3 ночи.
 1️⃣ Подтвердить
 2️⃣ Хочу всю комнату себе (приватно)
 3️⃣ Выбрать другие шконки
 4️⃣ Отмена"
       ↓
если (3): список свободных комнат с free_beds — гость выбирает номер
если (2): пересчитать как is_private_booking=True (если влезает) — показать цену
если (1): запрос имени → создание
```

**Новые состояния сессии:**
- `AWAIT_BED_CONFIRM` — показали preview, ждём выбор 1/2/3/4
- `AWAIT_ROOM_CHOICE` — ждём выбор комнаты из списка (если нажал 3)

**Хранится в `session.data`:**
- `preview_bed_ids: [45, 46, 47, 48]` — что предложила система
- `preview_total: 6000`
- `is_private: False`

---

## 7. Этапы разработки (4 фазы)

### Этап 1: Модель + миграция данных (скрытно, продакшен не трогаем)
- Новые модели `Bed`, `BookingBed`
- Data-migration: генерация `Bed` из `Room.capacity`, заполнение `BookingBed` для
  исторических броней
- **Код пока читает и пишет только старое поле `Booking.room`** — новые таблицы
  существуют, но не используются
- **Verify:** `python manage.py migrate` проходит; старая система работает;
  `SELECT COUNT(*) FROM booking_bed` = `SUM(guests) FROM active bookings`

### Этап 2: Параллельный сервис (feature flag)
- Реализовать `get_available_beds`, `auto_assign_beds`, `create_booking_with_beds`
- Новый endpoint `/api/bookings/v2/` — использует новый сервис
- Старый `/api/bookings/` остаётся на старой логике
- **Двойная запись:** при любом создании брони (и через v1, и через v2) заполняются
  **оба** `Booking.room` И `BookingBed` — чтобы при переключении фронта/бота
  ничего не сломалось
- **Verify:** тесты на `create_booking_with_beds` (race, приватность, группы 10+);
  endpoint `/v2/` создаёт правильные данные; старый endpoint всё ещё работает

### Этап 3: Переключить клиентов
- Фронт → на `/api/bookings/v2/` + показ `beds` в дашборде
- WA-бот → новый флоу с preview и выбором приватной комнаты
- iCal export → блокировка Room если хоть одна шконка занята активной бронью
- iCal import → при импорте блокирует всю Room (внешний агрегатор не знает про шконки)
- **Verify:** все боты и фронт работают через v2; ручной тест группы 10 человек
  через WA проходит; iCal не отдаёт занятые комнаты свободными

### Этап 4: Legacy cleanup
- Удалить `Booking.room` из модели и ответов
- Удалить старый `/api/bookings/` (или 410 Gone)
- Удалить `get_booked_guests_by_type`
- **Verify:** `grep -r "Booking.room\b" apps/` пусто; `grep -r "get_booked_guests_by_type" apps/` пусто

---

## 8. Открытые вопросы — РЕШЕНЫ

Все 5 вопросов закрыты с Azat до старта Этапа 1.

### 1. Snapshot цен в BookingBed — ДА
`BookingBed.price_per_night` хранит снимок `Room.price_per_night` на момент
создания брони. Админ может менять `Room.price_per_night` для новых броней,
старые не дорожают/не дешевеют задним числом.

### 2. Денежные поля на Booking — УДАЛИТЬ `price_per_night`, ОСТАВИТЬ `total_price`
- `Booking.price_per_night` — **удаляется** (бессмысленно для броней со шконками
  разных цен)
- `Booking.total_price` — **остаётся** как snapshot итоговой суммы. Пересчитывается
  **только** в сервисе `create_booking_with_beds` и отдельном `recalculate_booking_total(booking)`
  для ручных правок. Никаких `pre_save`-сигналов в части пересчёта — урок из
  signals.py учтён.
- Детализация цен — через `beds: [{room, price_per_night}, ...]` в API-ответе.
  Фронт/бот сам решает как показывать.

### 3. `is_private_booking` на приватных комнатах — ИГНОРИРУЕМ
Флаг `is_private_booking` имеет смысл только для дорм-комнат (`price_is_per_bed=True`).
Для приватных (`single`, `double_together`, `double_separate`) бронирование итак
приватно по определению. Сервис не бросает ошибку — просто игнорирует флаг, даже
если фронт/бот его прислал `True`. В БД поле может быть `True`/`False` для приватных,
но ни на что не влияет.

### 4. Проверка цен в Room перед миграцией — AZAT ПРОСТАВИТ САМ
Заказчик скинет актуальные цены по каждой комнате. Аzat проставляет их в
`Room.price_per_night` через Django-админку **до старта Этапа 1**. Миграция
данных увидит уже правильные цены и сохранит их в `BookingBed.price_per_night`
для исторических броней.

**Блокер Этапа 1:** до того как писать миграцию — убедиться что Azat завёр все цены.

### 5. UX при отказе private в WA-боте — ВАРИАНТ A (коротко)
Если гость нажал «хочу приватно» и в этом типе нет свободных комнат
целиком — бот отвечает коротко и предлагает вернуться к уже найденному
автоподбору:

> Сейчас нет свободных комнат этого типа целиком на ваши даты.
> Можете взять {N} шконок (как сначала показали) — подтвердить?
> 1️⃣ Подтвердить
> 2️⃣ Отмена

Не показываем альтернативные типы (дорм-6 вместо дорм-4) и альтернативные даты —
это отдельные фичи, не в MVP.

---

## 9. Что НЕ в этом scope (делается отдельно или потом)

- Скидки за длительное проживание
- Тарифы выходного дня / сезонные цены
- Выбор конкретной шконки "нижняя/верхняя" с отдельной ценой
- Объединение броней (приехали 2 человека, подсели ещё 2 в ту же комнату)
- Интеграция с Booking.com как **канал** (сейчас только импорт .ics)
- Овербукинг

---

## 10. Verify перед стартом Этапа 1

Перед тем как писать код:
- [x] Azat прочитал этот документ
- [x] Открытые вопросы из §8 закрыты
- [x] Согласован порядок этапов (Этап 1 → 2 → 3 → 4, не пропускать)
- [ ] **Блокер:** Azat проставил актуальные цены в `Room.price_per_night` через
  Django-админку (заказчик скинет)
- [ ] Зафиксирован момент когда включаем v2 на проде (после Этапа 3)

После этого — создаём задачу на Этап 1 в Claude Code с чёткой формулировкой scope.
