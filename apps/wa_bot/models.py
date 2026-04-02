from django.db import models

class WhatsAppSession(models.Model):
    class State(models.TextChoices):
        START = "start", "Начало"
        AWAIT_BRANCH = "await_branch", "Ожидает выбор филиала"
        AWAIT_DATES = "await_dates", "Ожидает даты заезда/выезда"
        AWAIT_GUESTS = "await_guests", "Ожидает количество гостей"
        AWAIT_ROOM = "await_room", "Ожидает тип номера"
        AWAIT_NAME = "await_name", "Ожидает имя"

    phone = models.CharField(max_length=30, unique=True, verbose_name="Номер WhatsApp")
    state = models.CharField(max_length=20, choices=State.choices, default=State.START)
    data = models.JSONField(default=dict, blank=True, verbose_name="Данные сессии")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Сессия WhatsApp"
        verbose_name_plural = "Сессии WhatsApp"

    def __str__(self):
        return f"{self.phone} - {self.get_state_display()}"
