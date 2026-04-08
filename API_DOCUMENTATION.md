# 📖 KonoQ Hostel - Frontend API Documentation

Это полная техническая документация бэкенда для интеграции Frontend приложения. Ниже описан абсолютно **каждый** существующий эндпоинт.

> [!NOTE]
> **Base URL:** `https://konoq-hostel.com/api`  
> **Headers:** `Content-Type: application/json`  
> **Auth Header:** `Authorization: Bearer <access_token>` (для защищенных эндпоинтов)

---

## 🔐 1. Авторизация (Auth)
Модуль для управления доступом Менеджеров и Владельцев. Базируется на JWT.

### 1.1 Вход (Login)
`POST https://konoq-hostel.com/api/auth/login/`
- **Доступ:** Публичный
- **Описание:** Получение JWT токенов по логину/паролю.
- **Request:**
```json
{
  "username": "manager1",
  "password": "secretpassword"
}
```
- **Response (200 OK):**
```json
{
  "access": "eyJhb...",
  "refresh": "eyJhb...",
  "user": {
    "id": 1,
    "username": "manager1",
    "role": "manager",
    "role_display": "Менеджер"
  }
}
```

### 1.2 Получение текущего юзера
`GET https://konoq-hostel.com/api/auth/me/`
- **Доступ:** `IsAuthenticated` (Требуется `Bearer` токен)
- **Response (200 OK):**
```json
{
  "id": 1,
  "username": "manager1",
  "role": "manager",
  "role_display": "Менеджер",
  "branch": 1 
}
```

### 1.3 Обновление токена (Refresh)
`POST https://konoq-hostel.com/api/auth/token/refresh/`
- **Доступ:** Публичный
- **Описание:** Вызывать, когда access токен устарел (вернулся статус 401).
- **Request:**
```json
{
  "refresh": "ВАШ_СТАРЫЙ_РЕФРЕШ_ТОКЕН"
}
```
- **Response (200 OK):** `{"access": "новый", "refresh": "новый"}`

### 1.4 Выход (Logout)
`POST https://konoq-hostel.com/api/auth/logout/`
- **Доступ:** `IsAuthenticated`
- **Описание:** Отправляет refresh токен в Blacklist.
- **Request:** `{"refresh": "ТОКЕН"}`
- **Response:** `200 OK`, пусто.

### 1.5 Смена пароля
`POST https://konoq-hostel.com/api/auth/change-password/`
- **Доступ:** `IsAuthenticated`
- **Request:** `{"old_password": "старый", "new_password": "новый"}`
- **Response:** `200 OK`

---

## 📅 2. Бронирования (Bookings)

### 2.1 Создать новую бронь (Для сайта)
`POST https://konoq-hostel.com/api/bookings/create/`
- **Доступ:** Публичный
- **Описание:** Вызвать при отправке формы клиентом на сайте. Статус всегда `pending`.
- **Request:**
```json
{
  "fullname": "Иван Иванов", 
  "phone": "+996555111222",
  "email": "ivan@mail.com",
  "checkin": "2026-05-10",
  "checkout": "2026-05-15",
  "guests": 2,
  "room": "dorm_4", 
  "country": "Россия",
  "purpose": "tourism",
  "comment": "Поздний заезд в 23:00"
}
```
*`room` варианты: `single`, `dorm_2`, `dorm_4`, `dorm_6`, `dorm_8`, `double_together`, `double_separate`.*
*`purpose` варианты: `tourism`, `business`, `transit`, `study`, `family`, `other`.*
- **Response (201 Created):** Объект бронирования.

### 2.2 Получить список броней (Менеджер)
`GET https://konoq-hostel.com/api/bookings/`
- **Доступ:** `IsAuthenticated`
- **Описание:** Дашборд менеджера со списком всех заявок. Сортируются от новых к старым.
- **Response:** 
```json
[
  {
    "id": 10,
    "name": "Иван",
    "surname": "Иванов",
    "phone": "+996...",
    "checkin": "2026-05-10",
    "checkout": "2026-05-15",
    "nights": 5,
    "guests": 2,
    "room": "dorm_4",
    "room_display": "Дорм 4-местный",
    "purpose_display": "Туризм",
    "source": "direct",
    "source_display": "Прямое (сайт)",
    "branch_name": "Главный",
    "status": "pending",
    "status_display": "Ожидает",
    "created_at": "2026-04-03T10:00:00Z"
  }
]
```

### 2.3 Детали бронирования
`GET https://konoq-hostel.com/api/bookings/<id>/`
- **Доступ:** `IsAuthenticated`
- **Response:** Тот же объект, что и в 2.2, но детальный.

### 2.4 Изменить статус / Обновить данные
`PATCH https://konoq-hostel.com/api/bookings/<id>/`
- **Доступ:** `IsAuthenticated`
- **Описание:** Изменение статуса: Подтверждение или Отмена. Под капотом инициирует автоматическую рассылку в WhatsApp клиенту.
- **Request:**
```json
{
  "status": "confirmed"  
}
```
*Варианты статусов: `pending`, `confirmed`, `cancelled`.*
- **Response:** Обновленный объект брони.

### 2.5 Краткая статистика статусов
`GET https://konoq-hostel.com/api/bookings/stats/`
- **Доступ:** `IsAuthenticated`
- **Response:** `{"total": 15, "pending": 5, "confirmed": 8, "cancelled": 2}`

---

## 🏨 3. Филиалы (Branches)

### 3.1 Список филиалов
`GET https://konoq-hostel.com/api/rooms/branch/`
- **Доступ:** `IsAuthenticated`
- **Response:**
```json
[
  {
    "id": 1,
    "name": "Главный",
    "address": "Чуй 12",
    "is_active": true
  }
]
```

### 3.2 Добавить филиал
`POST https://konoq-hostel.com/api/rooms/branch/`
- **Доступ:** `IsAuthenticated`

### 3.3 Обновить / Удалить филиал
`PATCH https://konoq-hostel.com/api/rooms/branch/<id>/`
`DELETE https://konoq-hostel.com/api/rooms/branch/<id>/`
- **Доступ:** `IsAuthenticated`

---

## 🛏 4. Номера (Rooms)

Базовый каталог комнат. Очень важен функционал вычисления свободных мест.

### 4.1 Получить список доступных комнат (Для сайта / календаря)
`GET https://konoq-hostel.com/api/rooms/?checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&branch=1`
- **Доступ:** Публичный / Менеджер
- **Важно:** Если передать `checkin` и `checkout`, бэкенд вычисляет `is_available` (хватит ли коек на эти даты).
- **Response:**
```json
[
  {
    "id": 1,
    "branch": 1,
    "number": "101",
    "room_type": "dorm_4",
    "room_type_display": "Дорм 4-местный",
    "capacity": 4,
    "price_per_night": 500.00,
    "price_is_per_bed": true,
    "has_bathroom": false,
    "description": "С окном",
    "is_available": true
  }
]
```

### 4.2 Создать комнату
`POST https://konoq-hostel.com/api/rooms/`
- **Доступ:** `IsAuthenticated`
- **Request:**
```json
{
  "branch": 1,
  "number": "105",
  "room_type": "single",
  "capacity": 1,
  "price_per_night": 1200.0,
  "price_is_per_bed": false,
  "has_bathroom": true
}
```

### 4.3 Обновить / Удалить комнату
`PATCH https://konoq-hostel.com/api/rooms/<id>/`  
`DELETE https://konoq-hostel.com/api/rooms/<id>/`  
- **Доступ:** `IsAuthenticated`

---

## 🏔 5. Туры (Tours)

### 5.1 Список активных туров (Публично)
`GET https://konoq-hostel.com/api/tours/public/`
- **Доступ:** Публичный
- **Описание:** Показывает только `is_active=true` туры.
- **Response:**
```json
[
  {
    "id": 1,
    "title": "Иссык-Куль Тур",
    "description": "Поездка на 3 дня",
    "price": "3000.00",
    "is_active": true
  }
]
```

### 5.2 Управление турами (Менеджер)
- `GET https://konoq-hostel.com/api/tours/` — показать ВСЕ туры (включая неактивные)
- `POST https://konoq-hostel.com/api/tours/` — создать тур (передать `title`, `description`, `price`, `is_active`)
- `PATCH https://konoq-hostel.com/api/tours/<id>/` — обновить информацию
- `DELETE https://konoq-hostel.com/api/tours/<id>/` — удалить тур
- **Доступ ко всем:** `IsAuthenticated`

---

## 🔄 6. iCal Синхронизация (Booking.com / Airbnb)

Блок для "общения" с агрегаторами. Фронтенд настраивает эти ссылки в интерфейсе.

### 6.1 ССЫЛКА НА ЭКСПОРТ (KonoQ ➡️ Airbnb)
**НЕ ТРЕБУЕТ ЗАГОЛОВКА AUTHORIZATION! Публично.**
`GET https://konoq-hostel.com/api/bookings/ical/export/<branch_id>/<room_type>/`
- **Пример:** `https://konoq-hostel.com/api/bookings/ical/export/1/double_together/`
- **Что происходит:** Возвращает скачиваемый файл `konoq_1_double_together.ics`. Фронтенд должен просто показывать эту ссылку Менеджеру как строку "Скопируйте и вставьте в Booking.com".

### 6.2 Добавить ссылку Airbnb/Booking в нашу базу (Импорт)
`POST https://konoq-hostel.com/api/bookings/ical/links/`
- **Доступ:** `IsAuthenticated`
- **Request:**
```json
{
  "branch": 1,
  "room_type": "double_together",
  "url": "https://www.airbnb.ru/calendar/ical/....ics",
  "source": "airbnb"
}
```

### 6.3 Получить список / Удалить ссылки iCal
- `GET https://konoq-hostel.com/api/bookings/ical/links/`
- `DELETE https://konoq-hostel.com/api/bookings/ical/links/<id>/`

### 6.4 Кнопка "Синхронизировать сейчас"
`POST https://konoq-hostel.com/api/bookings/ical/sync/`
- **Доступ:** `IsAuthenticated`
- **Описание:** Бэкенд за долю секунды обойдет все сохраненные ссылки (п. 6.2) и вытянет из них бронирования.
- **Response:**
```json
{
  "message": "Синхронизация завершена: 2 календарей обработано, 1 новых блокировок."
}
```

---

## 💰 7. Финансы (Только Владелец)

**ВАЖНО:** Для этих эндпоинтов токен должен принадлежать Владельцу (поле `role: "admin"`). Если токен Менеджера, вернется `403 Forbidden`.

Параметры `?month=X&year=YYYY` опциональны для всех ручек. Если не передать, берет текущий месяц.

### 7.1 Сводка (Finance Summary)
`GET https://konoq-hostel.com/api/finance/summary/?month=5&year=2026`
- **Response:** `{"month_name": "Май", "total_income": 150000.0, "target": 200000.0, "achievement_percent": 75.0, "diff": -50000.0}`

### 7.2 Цели (Таргеты)
`GET https://konoq-hostel.com/api/finance/targets/` (Список планов прибыли)
`POST https://konoq-hostel.com/api/finance/targets/`
- **Request:** `{"month": "2026-05-01", "target_revenue": 200000.0}`

### 7.3 Доходы по каналам
`GET https://konoq-hostel.com/api/finance/by-source/`
- **Response:**
```json
[
  {"source": "direct", "source_display": "Прямое (сайт)", "revenue": 10000.0},
  {"source": "airbnb", "source_display": "Airbnb", "revenue": 50000.0}
]
```

### 7.4 Доходы по филиалам
`GET https://konoq-hostel.com/api/finance/by-branch/`
- **Response:** `[{"branch__name": "Главный", "revenue": 60000.0}]`

### 7.5 Процент заселяемости (Occupancy)
`GET https://konoq-hostel.com/api/finance/occupancy/`
- **Response:** `{"occupancy_rate_percent": 65.4, "total_capacity_monthly": 1500, "total_guests_monthly": 981}`
