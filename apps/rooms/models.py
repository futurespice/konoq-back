"""
apps/rooms/models.py

Физические номера хостела. Каждый номер имеет тип, цену и вместимость.
"""
from django.db import models


class Room(models.Model):
    class RoomType(models.TextChoices):
        SINGLE = "Одноместный", "Одноместный"
        DOUBLE = "Двухместный", "Двухместный"
        FAMILY = "Семейный",    "Семейный"
        DORM   = "Дормитори",   "Дормитори"

    number          = models.CharField(max_length=10, unique=True, verbose_name="Номер комнаты")
    room_type       = models.CharField(max_length=20, choices=RoomType.choices, verbose_name="Тип")
    capacity        = models.PositiveSmallIntegerField(verbose_name="Вместимость")
    price_per_night = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Цена за ночь (сом)")
    description     = models.TextField(blank=True, default="", verbose_name="Описание")
    is_active       = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Номер"
        verbose_name_plural = "Номера"
        ordering = ["number"]

    def __str__(self):
        return f"№{self.number} · {self.room_type} · {self.price_per_night} сом/ночь"
