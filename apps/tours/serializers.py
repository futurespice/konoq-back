from rest_framework import serializers
from .models import Tour


class TourSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Tour
        fields = ["id", "name", "description", "price", "duration_hours",
                  "meeting_point", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
