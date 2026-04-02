"""
apps/tg_bot/apps.py
"""
from django.apps import AppConfig


class TgBotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name               = "apps.tg_bot"
    verbose_name       = "Telegram Bot"
