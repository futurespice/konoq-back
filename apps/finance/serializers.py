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
    """Выручка за один месяц — факт + план."""
    year         = serializers.IntegerField()
    month        = serializers.IntegerField()
    month_label  = serializers.CharField()
    actual       = serializers.DecimalField(max_digits=12, decimal_places=2)
    target       = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    bookings_count = serializers.IntegerField()


class FinanceSummarySerializer(serializers.Serializer):
    """Общая сводка для Влада."""
    total_revenue_all_time = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_this_month     = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_last_month     = serializers.DecimalField(max_digits=12, decimal_places=2)
    target_this_month      = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    confirmed_bookings_6m  = serializers.IntegerField()
    avg_stay_nights        = serializers.FloatField()
    monthly                = MonthlyRevenueSerializer(many=True)
