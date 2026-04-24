"""
apps/bookings/models.py
"""
from django.db import models


class Booking(models.Model):

    class Status(models.TextChoices):
        PENDING   = "pending",   "Ожидает"
        CONFIRMED = "confirmed", "Подтверждён"
        CANCELLED = "cancelled", "Отменён"

    class RoomType(models.TextChoices):
        SINGLE          = "single",          "Одноместная"
        DOUBLE          = "double",          "Двухместная"
        FAMILY          = "family",          "Семейная"
        DORMITORY       = "dormitory",       "Дормитори"
        DORM_2          = "dorm_2",          "Дорм 2-местный"
        DORM_4          = "dorm_4",          "Дорм 4-местный"
        DORM_6          = "dorm_6",          "Дорм 6-местный"
        DORM_8          = "dorm_8",          "Дорм 8-местный"
        DOUBLE_TOGETHER = "double_together", "Двухместная (вместе)"
        DOUBLE_SEPARATE = "double_separate", "Двухместная (раздельная)"

    class Purpose(models.TextChoices):
        TOURISM  = "tourism",  "Туризм"
        BUSINESS = "business", "Бизнес"
        TRANSIT  = "transit",  "Транзит"
        STUDY    = "study",    "Учёба"
        FAMILY   = "family",   "Семья / родственники"
        OTHER    = "other",    "Другое"

    class Source(models.TextChoices):
        DIRECT      = "direct",      "Прямое (сайт)"
        BOOKING_COM = "booking_com", "Booking.com"
        AIRBNB      = "airbnb",      "Airbnb"
        WALK_IN     = "walk_in",     "Walk-in"
        TELEGRAM    = "telegram",    "Telegram"
        WHATSAPP    = "whatsapp",    "WhatsApp"

    # ── Шаг 1: Личные данные ─────────────────────────────────────────────────
    name    = models.CharField(max_length=100, verbose_name="Имя")
    surname = models.CharField(max_length=100, verbose_name="Фамилия")
    phone   = models.CharField(max_length=30,  verbose_name="Телефон / WhatsApp")
    email   = models.EmailField(blank=True, default="", verbose_name="Email")

    # ── Шаг 2: Даты и номер ──────────────────────────────────────────────────
    checkin  = models.DateField(verbose_name="Дата заезда")
    checkout = models.DateField(verbose_name="Дата выезда")
    guests   = models.PositiveSmallIntegerField(default=1, verbose_name="Количество гостей")
    room = models.CharField(
        max_length=20,
        choices=RoomType.choices,
        blank=True,
        default="",
        verbose_name="Тип номера",
    )
    comment = models.TextField(blank=True, default="", verbose_name="Пожелания")

    # ── Шаг 3: Анкета ────────────────────────────────────────────────────────
    country = models.CharField(max_length=100, verbose_name="Страна прибытия")
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        verbose_name="Цель визита",
    )

    # ── Источник бронирования ────────────────────────────────────────────────
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.DIRECT,
        verbose_name="Источник",
    )

    # ── Филиал ───────────────────────────────────────────────────────────────
    branch = models.ForeignKey(
        "rooms.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
        verbose_name="Филиал",
    )

    # ── Статус (управляется менеджером) ──────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус",
    )

    # ── Финансы ──────────────────────────────────────────────────────────────
    price_per_night = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Цена за ночь"
    )
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Итоговая сумма"
    )

    is_private_booking = models.BooleanField(
        default=False,
        verbose_name="Забронировано целой комнатой",
        help_text="Группа забрала комнату целиком — чужих не подсаживаем",
    )

    # ── Служебные поля ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True,     verbose_name="Обновлено")

    class Meta:
        verbose_name = "Бронирование"
        verbose_name_plural = "Бронирования"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.name} {self.surname} | "
            f"{self.checkin} → {self.checkout} | "
            f"{self.get_status_display()}"
        )

    @property
    def nights(self):
        """Количество ночей."""
        return (self.checkout - self.checkin).days


class BookingBed(models.Model):
    """
    Привязка брони к конкретной шконке.

    checkin/checkout денормализованы (копия из Booking) для индексного
    поиска пересечений без JOIN.
    price_per_night — snapshot Room.price_per_night на момент создания брони.
    """
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="beds",
        verbose_name="Бронь",
    )
    bed = models.ForeignKey(
        "rooms.Bed",
        on_delete=models.PROTECT,
        related_name="bookings",
        verbose_name="Шконка",
    )
    checkin = models.DateField(verbose_name="Дата заезда")
    checkout = models.DateField(verbose_name="Дата выезда")
    price_per_night = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Цена за ночь (snapshot)",
    )

    class Meta:
        verbose_name = "Шконка в брони"
        verbose_name_plural = "Шконки в бронях"
        indexes = [
            models.Index(fields=["bed", "checkin", "checkout"]),
            models.Index(fields=["checkin", "checkout"]),
        ]


class ICalLink(models.Model):
    """Связь для импорта календарей из Booking/Airbnb."""
    class Source(models.TextChoices):
        AIRBNB      = "airbnb",      "Airbnb"
        BOOKING_COM = "booking_com", "Booking.com"

    branch = models.ForeignKey(
        "rooms.Branch",
        on_delete=models.CASCADE,
        related_name="ical_links",
        verbose_name="Филиал",
    )
    room_type = models.CharField(
        max_length=20,
        choices=Booking.RoomType.choices,
        verbose_name="Тип номера",
    )
    url = models.URLField(verbose_name="Ссылка на .ics (экспорт с агрегатора)", max_length=500)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        verbose_name="Платформа",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя синхронизация")

    class Meta:
        verbose_name = "iCal Календарь"
        verbose_name_plural = "iCal Календари"
        unique_together = ["branch", "room_type", "source"]

    def __str__(self):
        return f"{self.get_source_display()} - {self.branch.name} ({self.room_type})"

