"""
apps/finance/views.py

Финансовые данные — только для роли admin.
Выручка считается из подтверждённых бронирований × цена номера.

Эндпоинты:
  GET /api/finance/summary/            — общая сводка за 12 месяцев
  GET /api/finance/summary/?branch=1   — сводка по конкретному филиалу
  GET /api/finance/targets/            — план по месяцам (GET + POST)
  GET /api/finance/by-source/          — разбивка выручки по каналам
  GET /api/finance/by-branch/          — разбивка выручки по филиалам
  GET /api/finance/occupancy/          — загруженность номеров
"""
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from apps.bookings.models import Booking
from apps.rooms.models import Branch, Room
from .models import RevenueTarget
from .serializers import (
    FinanceSummarySerializer,
    RevenueTargetSerializer,
    MonthlyRevenueSerializer,
    BySourceSerializer,
    ByBranchSerializer,
    OccupancySerializer,
)

MONTH_NAMES_RU = [
    "", "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"
]

# ── Вспомогательные функции ────────────────────────────────────────────────────

def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin"


from django.db.models import Sum, Count

def _calc_revenue(qs) -> Decimal:
    """Суммарная выручка по queryset подтверждённых бронирований."""
    res = qs.aggregate(total=Sum("total_price"))["total"]
    return res if res else Decimal("0")


def _month_range(year: int, month: int):
    """Возвращает (first_day, last_day) для месяца."""
    first = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    last = date(year, month, last_day)
    return first, last


def _shift_month(year: int, month: int, delta: int):
    """Сдвигает месяц на delta (может быть отрицательным)."""
    total = (year * 12 + month - 1) + delta
    return total // 12, total % 12 + 1


def _monthly_data(months: int, branch_id=None) -> list:
    """Выручка факт+план за последние N месяцев."""
    today   = date.today()
    targets = {(t.year, t.month): t.target for t in RevenueTarget.objects.all()}
    result  = []

    for i in range(months - 1, -1, -1):
        y, m = _shift_month(today.year, today.month, -i)
        first, last = _month_range(y, m)

        qs = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin__gte=first,
            checkin__lte=last,
        )
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        actual = _calc_revenue(qs)
        result.append({
            "year":           y,
            "month":          m,
            "month_label":    f"{MONTH_NAMES_RU[m]} {y}",
            "actual":         actual,
            "target":         targets.get((y, m)),
            "bookings_count": qs.count(),
        })
    return result


# ── Views ──────────────────────────────────────────────────────────────────────

class FinanceSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Финансовая сводка (12 месяцев)",
        parameters=[
            OpenApiParameter("branch", OpenApiTypes.INT, description="Фильтр по филиалу (id)"),
        ],
        responses={200: FinanceSummarySerializer, 403: OpenApiResponse(description="Недостаточно прав")},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)

        today     = date.today()
        branch_id = request.query_params.get("branch")

        base_qs = Booking.objects.filter(
            status=Booking.Status.CONFIRMED
        ).select_related("branch")
        if branch_id:
            base_qs = base_qs.filter(branch_id=branch_id)

        # Текущий месяц
        this_month = base_qs.filter(checkin__year=today.year, checkin__month=today.month)

        # Прошлый месяц
        py, pm = _shift_month(today.year, today.month, -1)
        last_month = base_qs.filter(checkin__year=py, checkin__month=pm)

        # Всё время
        all_revenue = _calc_revenue(base_qs)

        # Средняя длительность
        avg_nights = 0.0
        if base_qs.exists():
            total_n = sum((b.checkout - b.checkin).days for b in base_qs)
            avg_nights = round(total_n / base_qs.count(), 1)

        # Средний чек за бронирование
        avg_booking_revenue = Decimal("0")
        if base_qs.exists():
            avg_booking_revenue = round(all_revenue / base_qs.count(), 2)

        # План на текущий месяц
        try:
            target_this = RevenueTarget.objects.get(year=today.year, month=today.month).target
        except RevenueTarget.DoesNotExist:
            target_this = None

        # Бронирований за последние 30 дней
        last_30 = base_qs.filter(checkin__gte=today - timedelta(days=30))

        data = {
            "total_revenue_all_time":    all_revenue,
            "revenue_this_month":        _calc_revenue(this_month),
            "revenue_last_month":        _calc_revenue(last_month),
            "target_this_month":         target_this,
            "confirmed_bookings_6m":     base_qs.filter(checkin__gte=today - timedelta(days=180)).count(),
            "confirmed_bookings_30d":    last_30.count(),
            "avg_stay_nights":           avg_nights,
            "avg_booking_revenue":       avg_booking_revenue,
            "monthly":                   _monthly_data(12, branch_id),
        }
        return Response(data)


class RevenueTargetView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Список плановых значений по месяцам",
        responses={200: RevenueTargetSerializer(many=True), 403: OpenApiResponse(description="Недостаточно прав")},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)
        return Response(RevenueTargetSerializer(RevenueTarget.objects.all(), many=True).data)

    @extend_schema(
        tags=["finance"],
        summary="Задать или обновить план на месяц",
        request=RevenueTargetSerializer,
        responses={200: RevenueTargetSerializer, 201: RevenueTargetSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)

        ser = RevenueTargetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj, created = RevenueTarget.objects.update_or_create(
            year=ser.validated_data["year"],
            month=ser.validated_data["month"],
            defaults={
                "target": ser.validated_data["target"],
                "note":   ser.validated_data.get("note", ""),
            },
        )
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(RevenueTargetSerializer(obj).data, status=code)


class BySourceView(APIView):
    """Разбивка бронирований и выручки по каналам за выбранный месяц."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Выручка по каналам (источникам)",
        parameters=[
            OpenApiParameter("year",   OpenApiTypes.INT, description="Год (по умолчанию текущий)"),
            OpenApiParameter("month",  OpenApiTypes.INT, description="Месяц (по умолчанию текущий)"),
            OpenApiParameter("branch", OpenApiTypes.INT, description="Фильтр по филиалу"),
        ],
        responses={200: BySourceSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)

        today     = date.today()
        try:
            year      = int(request.query_params.get("year",  today.year))
            month     = int(request.query_params.get("month", today.month))
        except ValueError:
            return Response({"detail": "Неверный формат даты."}, status=status.HTTP_400_BAD_REQUEST)
        branch_id = request.query_params.get("branch")

        first, last = _month_range(year, month)
        qs = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin__gte=first,
            checkin__lte=last,
        ).select_related("branch")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        # Группируем по source
        by_source = {}
        for b in qs:
            src = b.source
            if src not in by_source:
                by_source[src] = {"source": src, "source_display": b.get_source_display(), "count": 0, "revenue": Decimal("0")}
            by_source[src]["count"]   += 1
            by_source[src]["revenue"] += b.total_price

        result = sorted(by_source.values(), key=lambda x: x["revenue"], reverse=True)
        return Response(result)


class ByBranchView(APIView):
    """Разбивка бронирований и выручки по филиалам за выбранный месяц."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Выручка по филиалам",
        parameters=[
            OpenApiParameter("year",  OpenApiTypes.INT, description="Год"),
            OpenApiParameter("month", OpenApiTypes.INT, description="Месяц"),
        ],
        responses={200: ByBranchSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)

        today = date.today()
        try:
            year  = int(request.query_params.get("year",  today.year))
            month = int(request.query_params.get("month", today.month))
        except ValueError:
            return Response({"detail": "Неверный формат даты."}, status=status.HTTP_400_BAD_REQUEST)

        first, last = _month_range(year, month)
        qs = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            checkin__gte=first,
            checkin__lte=last,
        ).select_related("branch")

        by_branch = {}
        for b in qs:
            key  = b.branch_id or 0
            name = b.branch.name if b.branch else "Не указан"
            if key not in by_branch:
                by_branch[key] = {"branch_id": key, "branch_name": name, "count": 0, "revenue": Decimal("0")}
            by_branch[key]["count"]   += 1
            by_branch[key]["revenue"] += b.total_price

        result = sorted(by_branch.values(), key=lambda x: x["revenue"], reverse=True)
        return Response(result)


class OccupancyView(APIView):
    """
    Загруженность (occupancy) по филиалу за месяц.
    occupancy = подтверждённые гости-ночи / (кол-во мест × дней в месяце)
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance"],
        summary="Загруженность по филиалам",
        parameters=[
            OpenApiParameter("year",  OpenApiTypes.INT, description="Год"),
            OpenApiParameter("month", OpenApiTypes.INT, description="Месяц"),
        ],
        responses={200: OccupancySerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Доступ только для администраторов."}, status=status.HTTP_403_FORBIDDEN)

        today = date.today()
        try:
            year  = int(request.query_params.get("year",  today.year))
            month = int(request.query_params.get("month", today.month))
        except ValueError:
            return Response({"detail": "Неверный формат даты."}, status=status.HTTP_400_BAD_REQUEST)
        first, last = _month_range(year, month)
        days_in_month = monthrange(year, month)[1]

        result = []
        for branch in Branch.objects.filter(is_active=True):
            rooms = Room.objects.filter(branch=branch, is_active=True)
            total_beds = sum(r.capacity for r in rooms)

            if total_beds == 0:
                continue

            # Гости-ночи = сумма (guests × nights) по всем подтверждённым за месяц
            bookings = Booking.objects.filter(
                status=Booking.Status.CONFIRMED,
                branch=branch,
                checkin__lte=last,
                checkout__gt=first,
            )
            guest_nights = sum(
                b.guests * min((b.checkout - b.checkin).days, days_in_month)
                for b in bookings
            )

            max_guest_nights = total_beds * days_in_month
            occupancy_pct = round(guest_nights / max_guest_nights * 100, 1) if max_guest_nights else 0.0

            result.append({
                "branch_id":       branch.id,
                "branch_name":     branch.name,
                "total_beds":      total_beds,
                "guest_nights":    guest_nights,
                "max_nights":      max_guest_nights,
                "occupancy_pct":   occupancy_pct,
            })

        return Response(result)
