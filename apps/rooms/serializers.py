"""
apps/rooms/serializers.py
"""
from rest_framework import serializers
from .models import Branch, Room


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Branch
        fields = ["id", "name", "address", "is_active"]


class RoomSerializer(serializers.ModelSerializer):
    room_type_display = serializers.CharField(source="get_room_type_display", read_only=True)
    branch_name       = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model  = Room
        fields = [
            "id", "branch", "branch_name",
            "number", "room_type", "room_type_display",
            "capacity", "price_per_night", "price_is_per_bed",
            "has_bathroom", "description", "is_active",
        ]


class RoomAvailabilitySerializer(RoomSerializer):
    """Номер + флаг свободен ли в выбранный период."""
    is_available = serializers.BooleanField(read_only=True)

    class Meta(RoomSerializer.Meta):
        fields = RoomSerializer.Meta.fields + ["is_available"]


class RoomWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Room
        fields = [
            "branch", "number", "room_type",
            "capacity", "price_per_night", "price_is_per_bed",
            "has_bathroom", "description", "is_active",
        ]
