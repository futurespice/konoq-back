"""
apps/rooms/migrations/0002_branch_room_refactor.py

Добавляет:
  - модель Branch
  - поле branch (FK) на Room
  - поле has_bathroom на Room
  - поле price_is_per_bed на Room
  - обновляет choices у room_type (max_length остаётся 20)
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0001_initial"),
    ]

    operations = [
        # 1. Создаём модель Branch
        migrations.CreateModel(
            name="Branch",
            fields=[
                ("id",        models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name",      models.CharField(max_length=100, unique=True, verbose_name="Название")),
                ("address",   models.TextField(blank=True, default="", verbose_name="Адрес")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
            ],
            options={
                "verbose_name":        "Филиал",
                "verbose_name_plural": "Филиалы",
                "ordering":            ["name"],
            },
        ),

        # 2. Добавляем branch (nullable сначала — заполним в seed)
        migrations.AddField(
            model_name="room",
            name="branch",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rooms",
                to="rooms.branch",
                verbose_name="Филиал",
            ),
        ),

        # 3. has_bathroom
        migrations.AddField(
            model_name="room",
            name="has_bathroom",
            field=models.BooleanField(default=False, verbose_name="Собственный санузел"),
        ),

        # 4. price_is_per_bed
        migrations.AddField(
            model_name="room",
            name="price_is_per_bed",
            field=models.BooleanField(
                default=False,
                verbose_name="Цена за место (шконку)",
                help_text="True для дормов: клиент платит за место, а не за всю комнату",
            ),
        ),

        # 5. Обновляем choices у room_type (только Python-level, без изменения столбца)
        migrations.AlterField(
            model_name="room",
            name="room_type",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("dorm_2",          "Дорм 2-местный (шконки)"),
                    ("dorm_4",          "Дорм 4-местный (шконки)"),
                    ("dorm_6",          "Дорм 6-местный (шконки)"),
                    ("dorm_8",          "Дорм 8-местный (шконки)"),
                    ("double_together", "Двухместная (вместе)"),
                    ("double_separate", "Двухместная (раздельная)"),
                ],
                verbose_name="Тип",
            ),
        ),

        # 6. Упорядочиваем по филиалу + номеру
        migrations.AlterModelOptions(
            name="room",
            options={
                "verbose_name":        "Номер",
                "verbose_name_plural": "Номера",
                "ordering":            ["branch", "number"],
            },
        ),
    ]
