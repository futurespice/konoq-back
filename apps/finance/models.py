"""
apps/finance/models.py

Плановая выручка по месяцам — Влад задаёт цели, система считает факт.
"""
from django.db import models


class RevenueTarget(models.Model):
    """Плановая выручка на месяц."""
    year   = models.PositiveSmallIntegerField(verbose_name="Год")
    month  = models.PositiveSmallIntegerField(verbose_name="Месяц (1–12)")
    target = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="План (сом)")
    note   = models.CharField(max_length=300, blank=True, default="", verbose_name="Заметка")

    class Meta:
        unique_together = [["year", "month"]]
        verbose_name = "Плановая выручка"
        verbose_name_plural = "Плановая выручка"
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"{self.year}-{self.month:02d} · план {self.target} сом"
