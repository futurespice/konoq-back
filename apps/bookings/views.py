"""
apps/bookings/views.py
"""
import asyncio
import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema, OpenApiResponse, OpenApiParameter, OpenApiExample
)
from drf_spectacular.types import OpenApiTypes

from .models import Booking
from .serializers import (
    BookingCreateSerializer,
    BookingListSerializer,
    BookingStatusUpdateSerializer,
    BookingStatsSerializer,
)

logger = logging.getLogger(__name__)


def _send_tg_notification(booking):
    """Отправляет Telegram-уведомление о новом бронировании (в фоне)."""
    import threading
    def _run():
        try:
            from apps.tg_bot.bot import notify_owner_new_booking
            asyncio.run(notify_owner_new_booking(booking))
        except Exception as exc:
            logger.warning("Не удалось отправить TG-уведомление: %s", exc)
    threading.Thread(target=_run, daemon=True).start()


class BookingCreateView(APIView):
    """
    Публичный эндпоинт — гость отправляет форму бронирования.
    """
    authentication_classes = []  # Не аутентифицируем вообще — иначе просроченный токен в localStorage вызывает 401
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["bookings"],
        summary="Создать бронирование",
        description=(
            "Публичный эндпоинт. Гость заполняет форму и отправляет заявку. "
            "Статус автоматически выставляется в `pending`. "
            "Владелец получит уведомление в Telegram."
        ),
        request=BookingCreateSerializer,
        responses={
            201: BookingListSerializer,
            400: OpenApiResponse(description="Ошибка валидации"),
        },
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "fullname": "Artur Dzhaksybekov",
                    "phone": "+996 700 000 000",
                    "email": "artur@mail.com",
                    "checkin": "2026-05-10",
                    "checkout": "2026-05-14",
                    "guests": 2,
                    "room": "dorm_6",
                    "comment": "Желательно нижняя шконка",
                    "country": "Кыргызстан",
                    "purpose": "tourism",
                    "source": "direct",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()

        # Уведомляем владельца в Telegram
        _send_tg_notification(booking)

        return Response(
            BookingListSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


class BookingListView(APIView):
    """
    Список всех бронирований — только для авторизованных менеджеров.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["bookings"],
        summary="Список бронирований",
        parameters=[
            OpenApiParameter("status",  OpenApiTypes.STR,  description="pending | confirmed | cancelled"),
            OpenApiParameter("source",  OpenApiTypes.STR,  description="direct | booking_com | airbnb | walk_in | telegram"),
            OpenApiParameter("branch",  OpenApiTypes.INT,  description="ID филиала"),
            OpenApiParameter("search",  OpenApiTypes.STR,  description="Поиск по имени, телефону, стране"),
            OpenApiParameter("checkin", OpenApiTypes.DATE, description="Заезд от этой даты (YYYY-MM-DD)"),
        ],
        responses={200: BookingListSerializer(many=True)},
    )
    def get(self, request):
        qs = Booking.objects.select_related("branch").all()

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        source_filter = request.query_params.get("source")
        if source_filter:
            qs = qs.filter(source=source_filter)

        branch_filter = request.query_params.get("branch")
        if branch_filter:
            qs = qs.filter(branch_id=branch_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)    |
                Q(surname__icontains=search) |
                Q(phone__icontains=search)   |
                Q(country__icontains=search)
            )

        checkin_from = request.query_params.get("checkin")
        if checkin_from:
            qs = qs.filter(checkin__gte=checkin_from)

        return Response(BookingListSerializer(qs, many=True).data)


class BookingDetailView(APIView):
    """Получить / обновить статус / удалить одно бронирование."""
    permission_classes = [IsAuthenticated]

    def _get_booking(self, pk):
        try:
            return Booking.objects.select_related("branch").get(pk=pk)
        except Booking.DoesNotExist:
            return None

    @extend_schema(
        tags=["bookings"],
        summary="Детали бронирования",
        responses={200: BookingListSerializer, 404: OpenApiResponse(description="Не найдено")},
    )
    def get(self, request, pk):
        booking = self._get_booking(pk)
        if not booking:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BookingListSerializer(booking).data)

    @extend_schema(
        tags=["bookings"],
        summary="Обновить статус бронирования",
        request=BookingStatusUpdateSerializer,
        responses={
            200: BookingListSerializer,
            400: OpenApiResponse(description="Недопустимый статус"),
            404: OpenApiResponse(description="Не найдено"),
        },
        examples=[
            OpenApiExample("Подтвердить", value={"status": "confirmed"}, request_only=True),
            OpenApiExample("Отменить",    value={"status": "cancelled"}, request_only=True),
        ],
    )
    def patch(self, request, pk):
        booking = self._get_booking(pk)
        if not booking:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BookingStatusUpdateSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BookingListSerializer(booking).data)

    @extend_schema(
        tags=["bookings"],
        summary="Удалить бронирование",
        responses={204: OpenApiResponse(description="Удалено"), 404: OpenApiResponse(description="Не найдено")},
    )
    def delete(self, request, pk):
        booking = self._get_booking(pk)
        if not booking:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        booking.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BookingStatsView(APIView):
    """Статистика для дашборда."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["bookings"],
        summary="Статистика бронирований",
        parameters=[
            OpenApiParameter("branch", OpenApiTypes.INT, description="Фильтр по филиалу (id)"),
        ],
        responses={200: BookingStatsSerializer},
    )
    def get(self, request):
        qs = Booking.objects.all()

        branch_id = request.query_params.get("branch")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        data = {
            "total":     qs.count(),
            "pending":   qs.filter(status=Booking.Status.PENDING).count(),
            "confirmed": qs.filter(status=Booking.Status.CONFIRMED).count(),
            "cancelled": qs.filter(status=Booking.Status.CANCELLED).count(),
        }
        return Response(data)
