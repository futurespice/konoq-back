"""
apps/users/models.py

Кастомный User — расширяем стандартный AbstractUser.
Роли: manager (менеджер хостела), admin (супер-администратор).
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер"
        ADMIN   = "admin",   "Администратор"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MANAGER,
        verbose_name="Роль",
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Телефон",
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["username"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN
