"""
apps/rooms/models.py

Физические номера хостела.
Branch — филиал (Ош / Второй филиал и т.д.)
Room   — конкретная комната с типом, ценой и вместимостью.
"""
from django.db import models


class Branch(models.Model):
    """Филиал хостела."""
    name      = models.CharField(max_length=100, unique=True, verbose_name="Название")
    address   = models.TextField(blank=True, default="", verbose_name="Адрес")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Филиал"
        verbose_name_plural = "Филиалы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Room(models.Model):
    class RoomType(models.TextChoices):
        SINGLE          = "single",          "Одноместная"
        DORM_2          = "dorm_2",          "Дорм 2-местный (шконки)"
        DORM_4          = "dorm_4",          "Дорм 4-местный (шконки)"
        DORM_6          = "dorm_6",          "Дорм 6-местный (шконки)"
        DORM_8          = "dorm_8",          "Дорм 8-местный (шконки)"
        DOUBLE_TOGETHER = "double_together", "Двухместная (вместе)"
        DOUBLE_SEPARATE = "double_separate", "Двухместная (раздельная)"

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="rooms",
        verbose_name="Филиал",
    )
    number          = models.CharField(max_length=10, unique=True, verbose_name="Номер комнаты")
    room_type       = models.CharField(
        max_length=20,
        choices=RoomType.choices,
        verbose_name="Тип",
    )
    capacity        = models.PositiveSmallIntegerField(verbose_name="Вместимость (чел.)")
    price_per_night = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Цена за ночь (сом)",
        help_text="Для дормов — цена за одну шконку/место",
    )
    price_is_per_bed = models.BooleanField(
        default=False,
        verbose_name="Цена за место (шконку)",
        help_text="True для дормов: клиент платит за место, а не за всю комнату",
    )
    image        = models.ImageField(
        upload_to="rooms/",
        blank=True,
        null=True,
        verbose_name="Изображение",
    )
    has_bathroom = models.BooleanField(default=False, verbose_name="Собственный санузел")
    description  = models.TextField(blank=True, default="", verbose_name="Описание")
    is_active    = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        verbose_name = "Номер"
        verbose_name_plural = "Номера"
        ordering = ["branch", "number"]

    def __str__(self):
        bath = " (с санузлом)" if self.has_bathroom else ""
        per  = "/место" if self.price_is_per_bed else "/ночь"
        return (
            f"[{self.branch.name}] №{self.number} · "
            f"{self.get_room_type_display()}{bath} · "
            f"{self.price_per_night} сом{per}"
        )
