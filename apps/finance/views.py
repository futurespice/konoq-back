"""
apps/finance/views.py

Финансовые данные — только для роли admin.
Выручка считается из подтверждённых бронирований × цена номера.
"""
from decimal import Decimal
from datetime import date, timedelta
from calendar import month_abbr

from django.db.models import Sum, Count, Avg, F
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from apps.bookings.models import Booking
from apps.rooms.models import Room
from .models import RevenueTarget
from .serializers import FinanceSummarySerializer, RevenueTargetSerializer, MonthlyRevenueSerializer

MONTH_NAMES_RU = [
    "", "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"
]


def _room_price(room_type: str) -> Decimal:
    """Цена за ночь для типа номера из таблицы Room."""
    room = Room.objects.filter(room_type=room_type, is_active=True).first()
    return room.price_per_night if room else Decimal("0")


def _calc_revenue_for_bookings(qs) -> Decimal:
    """Считает выручку по queryset бронирований."""
    total = Decimal("0")
    for b in qs.filter(status=Booking.Status.CONFIRMED):
        nights = (b.checkout - b.checkin).days
        price  = _room_price(b.room) if b.room else Decimal("0")
        total += nights * price
    return total


def _monthly_data(months: int) -> list:
    """Возвращает данные по выручке за последние N месяцев."""
    today    = date.today()
    result   = []
    targets  = {(t.year, t.month): t.target for t in RevenueTarget.objects.all()}

    for i in range(months - 1, -1, -1):
        # Вычисляем год/месяц со сдвигом
        m = (today.month - 1 - i) % 12 + 1
        y = today.year + ((today.month - 1 - i) // 12)

        # Первый и последний день месяца
        first = date(y, m, 1)
        if m == 12:
            last = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(y, m + 1, 1) - timedelta(days=1)

        month_bookings = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin__gte=first,
            checkin__lte=last,
        )
        actual = _calc_revenue_for_bookings(month_bookings)
        result.append({
            "year":            y,
            "month":           m,
            "month_label":     f"{MONTH_NAMES_RU[m]} {y}",
            "actual":          actual,
            "target":          targets.get((y, m)),
            "bookings_count":  month_bookings.count(),
        })
    return result


class FinanceSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Финансовая сводка",
        description="Полная финансовая картина за последние 12 месяцев. Только для admin.",
        responses={200: FinanceSummarySerializer, 403: OpenApiResponse(description="Недостаточно прав")},
    )
    def get(self, request):
        if request.user.role != "admin":
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)

        today = date.today()
        all_confirmed = Booking.objects.filter(status=Booking.Status.CONFIRMED)

        # Этот месяц
        this_month_qs = all_confirmed.filter(checkin__year=today.year, checkin__month=today.month)
        # Прошлый месяц
        pm = today.month - 1 or 12
        py = today.year if today.month > 1 else today.year - 1
        last_month_qs = all_confirmed.filter(checkin__year=py, checkin__month=pm)
        # Последние 6 месяцев
        six_months_ago = today - timedelta(days=180)
        last_6m_qs = all_confirmed.filter(checkin__gte=six_months_ago)

        # Средняя длительность
        avg_nights = 0.0
        if all_confirmed.exists():
            total_n = sum((b.checkout - b.checkin).days for b in all_confirmed)
            avg_nights = round(total_n / all_confirmed.count(), 1)

        # План на этот месяц
        try:
            target_obj = RevenueTarget.objects.get(year=today.year, month=today.month)
            target_this = target_obj.target
        except RevenueTarget.DoesNotExist:
            target_this = None

        data = {
            "total_revenue_all_time": _calc_revenue_for_bookings(all_confirmed),
            "revenue_this_month":     _calc_revenue_for_bookings(this_month_qs),
            "revenue_last_month":     _calc_revenue_for_bookings(last_month_qs),
            "target_this_month":      target_this,
            "confirmed_bookings_6m":  last_6m_qs.count(),
            "avg_stay_nights":        avg_nights,
            "monthly":                _monthly_data(12),
        }
        return Response(data)


class RevenueTargetView(APIView):
    """CRUD для плановой выручки."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["finance"], summary="Список плановых значений", responses={200: RevenueTargetSerializer(many=True)})
    def get(self, request):
        if request.user.role != "admin":
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)
        targets = RevenueTarget.objects.all()
        return Response(RevenueTargetSerializer(targets, many=True).data)

    @extend_schema(
        tags=["finance"], summary="Задать план на месяц",
        request=RevenueTargetSerializer,
        responses={200: RevenueTargetSerializer, 201: RevenueTargetSerializer},
    )
    def post(self, request):
        if request.user.role != "admin":
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)
        ser = RevenueTargetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        obj, created = RevenueTarget.objects.update_or_create(
            year=ser.validated_data["year"],
            month=ser.validated_data["month"],
            defaults={"target": ser.validated_data["target"], "note": ser.validated_data.get("note", "")},
        )
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(RevenueTargetSerializer(obj).data, status=code)
