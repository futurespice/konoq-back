from django.db import models

class WhatsAppSession(models.Model):
    class State(models.TextChoices):
        START = "start", "Начало"
        AWAIT_LANG = "await_lang", "Ожидает язык"
        AWAIT_BRANCH = "await_branch", "Ожидает выбор филиала"
        AWAIT_DATES = "await_dates", "Ожидает даты заезда/выезда"
        AWAIT_GUESTS = "await_guests", "Ожидает количество гостей"
        AWAIT_PRIVATE_CHOICE = "await_private", "Ожидает выбор приватности"
        AWAIT_ROOM = "await_room", "Ожидает тип номера"
        AWAIT_BED_CONFIRM = "await_bed", "Ожидает подтверждение preview"
        AWAIT_ROOM_CHOICE = "await_room_choice", "Ожидает выбор конкретной комнаты"
        AWAIT_NAME = "await_name", "Ожидает имя"

    class Lang(models.TextChoices):
        RU = "ru", "Русский"
        EN = "en", "English"

    phone = models.CharField(max_length=30, unique=True, verbose_name="Номер WhatsApp")
    state = models.CharField(max_length=20, choices=State.choices, default=State.START)
    lang = models.CharField(max_length=5, choices=Lang.choices, default=Lang.RU)
    data = models.JSONField(default=dict, blank=True, verbose_name="Данные сессии")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Сессия WhatsApp"
        verbose_name_plural = "Сессии WhatsApp"

    def __str__(self):
        return f"{self.phone} - {self.get_state_display()}"


class WhatsAppProcessedEvent(models.Model):
    event_id = models.CharField(max_length=200, unique=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Обработанное событие WhatsApp"
        verbose_name_plural = "Обработанные события WhatsApp"

    def __str__(self):
        return self.event_id
