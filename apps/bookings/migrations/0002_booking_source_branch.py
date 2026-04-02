"""
apps/bookings/migrations/0002_booking_source_branch.py

Добавляет:
  - поле source (канал бронирования)
  - поле branch (FK → rooms.Branch, nullable)
  - обновляет choices у room (под новые типы номеров)
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0001_initial"),
        ("rooms",    "0002_branch_room_refactor"),
    ]

    operations = [
        # 1. Источник бронирования
        migrations.AddField(
            model_name="booking",
            name="source",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("direct",      "Прямое (сайт)"),
                    ("booking_com", "Booking.com"),
                    ("airbnb",      "Airbnb"),
                    ("walk_in",     "Walk-in"),
                    ("telegram",    "Telegram"),
                ],
                default="direct",
                verbose_name="Источник",
            ),
        ),

        # 2. FK на Branch (необязательный)
        migrations.AddField(
            model_name="booking",
            name="branch",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="rooms.branch",
                verbose_name="Филиал",
            ),
        ),

        # 3. Обновляем choices у room (типы номеров под новую структуру)
        migrations.AlterField(
            model_name="booking",
            name="room",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("dorm_2",          "Дорм 2-местный"),
                    ("dorm_4",          "Дорм 4-местный"),
                    ("dorm_6",          "Дорм 6-местный"),
                    ("dorm_8",          "Дорм 8-местный"),
                    ("double_together", "Двухместная (вместе)"),
                    ("double_separate", "Двухместная (раздельная)"),
                ],
                blank=True,
                default="",
                verbose_name="Тип номера",
            ),
        ),
    ]
