"""
apps/bookings/serializers.py
"""
from rest_framework import serializers
from .models import Booking


class BookingCreateSerializer(serializers.ModelSerializer):
    """
    Публичный сериализатор — используется для создания бронирования с фронта.

    Фронт может отправить либо:
      - fullname: "Иван Иванов"  (одно поле — как сейчас в Booking-компоненте)
      - name + surname раздельно (старый формат / Swagger)

    Статус гость не передаёт — он всегда 'pending'.
    source передаётся опционально (для walk-in, telegram и т.д.).
    """
    fullname = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Полное имя (если отправляется одним полем вместо name+surname)",
    )

    class Meta:
        model  = Booking
        fields = [
            "fullname",
            "name", "surname",
            "phone", "email",
            "checkin", "checkout", "guests", "room", "comment",
            "country", "purpose",
            "source", "branch",
        ]
        extra_kwargs = {
            "name":    {"required": False, "allow_blank": True},
            "surname": {"required": False, "allow_blank": True},
            "purpose": {"required": False, "default": "other"},
            "source":  {"required": False},
            "branch":  {"required": False},
        }

    def validate(self, attrs):
        # ── fullname → name + surname ──────────────────────────────
        fullname = attrs.pop("fullname", None)
        if fullname:
            parts = fullname.strip().split(None, 1)
            attrs["name"]    = parts[0]
            attrs["surname"] = parts[1] if len(parts) > 1 else ""

        if not attrs.get("name"):
            raise serializers.ValidationError(
                {"fullname": "Укажите имя (поле fullname или name)."}
            )

        # ── Проверка дат ───────────────────────────────────────────
        if attrs["checkin"] >= attrs["checkout"]:
            raise serializers.ValidationError(
                {"checkout": "Дата выезда должна быть позже даты заезда."}
            )

        # ── Проверка кол-ва гостей ────────────────────────────────
        if attrs["guests"] < 1 or attrs["guests"] > 20:
            raise serializers.ValidationError(
                {"guests": "Количество гостей должно быть от 1 до 20."}
            )

        return attrs


class BookingListSerializer(serializers.ModelSerializer):
    """
    Список бронирований для дашборда менеджера — все поля + вычисляемые.
    """
    status_display  = serializers.CharField(source="get_status_display",  read_only=True)
    room_display    = serializers.CharField(source="get_room_display",     read_only=True)
    purpose_display = serializers.CharField(source="get_purpose_display",  read_only=True)
    source_display  = serializers.CharField(source="get_source_display",   read_only=True)
    branch_name     = serializers.CharField(source="branch.name",          read_only=True)
    nights          = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Booking
        fields = [
            "id",
            "name", "surname", "phone", "email",
            "checkin", "checkout", "nights", "guests",
            "room", "room_display",
            "comment",
            "country",
            "purpose", "purpose_display",
            "source", "source_display",
            "branch", "branch_name",
            "status", "status_display",
            "created_at", "updated_at",
        ]


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    """Только для менеджера — смена статуса бронирования."""
    class Meta:
        model  = Booking
        fields = ["status"]

    def validate_status(self, value):
        allowed = [Booking.Status.CONFIRMED, Booking.Status.CANCELLED, Booking.Status.PENDING]
        if value not in allowed:
            raise serializers.ValidationError("Недопустимый статус.")
        return value


class BookingStatsSerializer(serializers.Serializer):
    """Статистика для дашборда — только для Swagger документации."""
    total     = serializers.IntegerField()
    pending   = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    cancelled = serializers.IntegerField()


class ICalLinkSerializer(serializers.ModelSerializer):
    """Сериализатор для работы со ссылками iCal (менеджер)."""
    room_type_display = serializers.CharField(source="get_room_type_display", read_only=True)
    source_display    = serializers.CharField(source="get_source_display",    read_only=True)
    branch_name       = serializers.CharField(source="branch.name",           read_only=True)

    class Meta:
        model  = __import__("apps.bookings.models", fromlist=["ICalLink"]).ICalLink
        fields = [
            "id", "branch", "branch_name",
            "room_type", "room_type_display",
            "url", "source", "source_display",
            "last_synced_at"
        ]
        read_only_fields = ["last_synced_at"]
