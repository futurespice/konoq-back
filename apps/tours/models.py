"""
apps/tours/models.py

Экскурсии и туры которые предлагает хостел гостям.
"""
from django.db import models


class Tour(models.Model):
    name          = models.CharField(max_length=200, verbose_name="Название")
    description   = models.TextField(blank=True, default="", verbose_name="Описание")
    price         = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Цена (сом/чел)")
    duration_hours = models.PositiveSmallIntegerField(verbose_name="Длительность (ч)")
    meeting_point = models.CharField(max_length=200, blank=True, default="", verbose_name="Место встречи")
    is_active     = models.BooleanField(default=True, verbose_name="Активен")
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тур"
        verbose_name_plural = "Туры"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} · {self.price} сом · {self.duration_hours}ч"
