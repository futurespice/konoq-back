"""
apps/bookings/serializers.py
"""
from rest_framework import serializers
from .models import Booking


class BookingCreateSerializer(serializers.ModelSerializer):
    """
    Публичный сериализатор — используется для создания бронирования с фронта.
    Статус гость не передаёт — он всегда 'pending'.
    """
    class Meta:
        model  = Booking
        fields = [
            "name", "surname", "phone", "email",
            "checkin", "checkout", "guests", "room", "comment",
            "country", "purpose",
        ]

    def validate(self, attrs):
        if attrs["checkin"] >= attrs["checkout"]:
            raise serializers.ValidationError(
                {"checkout": "Дата выезда должна быть позже даты заезда."}
            )
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
    room_display    = serializers.CharField(source="get_room_display",    read_only=True)
    purpose_display = serializers.CharField(source="get_purpose_display", read_only=True)
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
            "status", "status_display",
            "created_at", "updated_at",
        ]


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Только для менеджера — смена статуса бронирования.
    """
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
