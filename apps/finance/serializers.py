"""
apps/finance/serializers.py
"""
from rest_framework import serializers
from .models import RevenueTarget


class RevenueTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RevenueTarget
        fields = ["id", "year", "month", "target", "note"]

    def validate_month(self, value):
        if not 1 <= value <= 12:
            raise serializers.ValidationError("Месяц должен быть от 1 до 12.")
        return value


class MonthlyRevenueSerializer(serializers.Serializer):
    year           = serializers.IntegerField()
    month          = serializers.IntegerField()
    month_label    = serializers.CharField()
    actual         = serializers.DecimalField(max_digits=12, decimal_places=2)
    target         = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    bookings_count = serializers.IntegerField()


class FinanceSummarySerializer(serializers.Serializer):
    total_revenue_all_time   = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_this_month       = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_last_month       = serializers.DecimalField(max_digits=12, decimal_places=2)
    target_this_month        = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    confirmed_bookings_6m    = serializers.IntegerField()
    confirmed_bookings_30d   = serializers.IntegerField()
    avg_stay_nights          = serializers.FloatField()
    avg_booking_revenue      = serializers.DecimalField(max_digits=12, decimal_places=2)
    monthly                  = MonthlyRevenueSerializer(many=True)


class BySourceSerializer(serializers.Serializer):
    source         = serializers.CharField()
    source_display = serializers.CharField()
    count          = serializers.IntegerField()
    revenue        = serializers.DecimalField(max_digits=12, decimal_places=2)


class ByBranchSerializer(serializers.Serializer):
    branch_id   = serializers.IntegerField()
    branch_name = serializers.CharField()
    count       = serializers.IntegerField()
    revenue     = serializers.DecimalField(max_digits=12, decimal_places=2)


class OccupancySerializer(serializers.Serializer):
    branch_id     = serializers.IntegerField()
    branch_name   = serializers.CharField()
    total_beds    = serializers.IntegerField()
    guest_nights  = serializers.IntegerField()
    max_nights    = serializers.IntegerField()
    occupancy_pct = serializers.FloatField()
