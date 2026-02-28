from rest_framework import serializers
from .models import Room


class RoomSerializer(serializers.ModelSerializer):
    room_type_display = serializers.CharField(source="get_room_type_display", read_only=True)

    class Meta:
        model  = Room
        fields = ["id", "number", "room_type", "room_type_display",
                  "capacity", "price_per_night", "description", "is_active"]


class RoomAvailabilitySerializer(RoomSerializer):
    """Номер + флаг свободен ли в выбранный период."""
    is_available = serializers.BooleanField(read_only=True)

    class Meta(RoomSerializer.Meta):
        fields = RoomSerializer.Meta.fields + ["is_available"]


class RoomWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Room
        fields = ["number", "room_type", "capacity", "price_per_night", "description", "is_active"]
