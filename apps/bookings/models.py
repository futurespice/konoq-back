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
        # Значения совпадают с тем, что шлёт фронт (текст из <option> без value)
        SINGLE = "Одноместный", "Одноместный"
        DOUBLE = "Двухместный", "Двухместный"
        FAMILY = "Семейный",    "Семейный"
        DORM   = "Дормитори",   "Дормитори"

    class Purpose(models.TextChoices):
        # Значения совпадают с id из массива purposes на фронте
        TOURISM  = "tourism",  "Туризм"
        BUSINESS = "business", "Бизнес"
        TRANSIT  = "transit",  "Транзит"
        STUDY    = "study",    "Учёба"
        FAMILY   = "family",   "Семья / родственники"
        OTHER    = "other",    "Другое"

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

    # ── Статус (управляется менеджером) ───────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус",
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
