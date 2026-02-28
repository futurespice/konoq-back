"""
apps/bookings/views.py
"""
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


class BookingCreateView(APIView):
    """
    Публичный эндпоинт — гость отправляет форму бронирования.
    Авторизация НЕ нужна.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["bookings"],
        summary="Создать бронирование",
        description=(
            "Публичный эндпоинт. Гость заполняет форму и отправляет заявку. "
            "Статус автоматически выставляется в `pending`. "
            "Менеджер получит уведомление в дашборде."
        ),
        request=BookingCreateSerializer,
        responses={
            201: BookingListSerializer,
            400: OpenApiResponse(description="Ошибка валидации (неверные даты, пустые поля и т.д.)"),
        },
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "name": "Artur",
                    "surname": "Dzhaksybekov",
                    "phone": "+996 700 000 000",
                    "email": "artur@mail.com",
                    "checkin": "2026-03-10",
                    "checkout": "2026-03-14",
                    "guests": 2,
                    "room": "double",
                    "comment": "Желательно тихий номер",
                    "country": "Кыргызстан",
                    "purpose": "tourism",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(
            BookingListSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


class BookingListView(APIView):
    """
    Список всех бронирований — только для авторизованных менеджеров.
    Поддерживает фильтрацию и поиск.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["bookings"],
        summary="Список бронирований",
        description="Возвращает все бронирования. Доступен фильтр по статусу и поиск по имени/телефону/стране.",
        parameters=[
            OpenApiParameter("status",  OpenApiTypes.STR,  description="Фильтр: pending | confirmed | cancelled"),
            OpenApiParameter("search",  OpenApiTypes.STR,  description="Поиск по имени, телефону или стране"),
            OpenApiParameter("checkin", OpenApiTypes.DATE, description="Фильтр: заезд от этой даты (YYYY-MM-DD)"),
        ],
        responses={200: BookingListSerializer(many=True)},
    )
    def get(self, request):
        qs = Booking.objects.all()

        # Фильтр по статусу
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        # Поиск
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(surname__icontains=search) |
                Q(phone__icontains=search) |
                Q(country__icontains=search)
            )

        # Фильтр по дате заезда
        checkin_from = request.query_params.get("checkin")
        if checkin_from:
            qs = qs.filter(checkin__gte=checkin_from)

        serializer = BookingListSerializer(qs, many=True)
        return Response(serializer.data)


class BookingDetailView(APIView):
    """
    Получить / обновить статус / удалить одно бронирование.
    Только для авторизованных.
    """
    permission_classes = [IsAuthenticated]

    def _get_booking(self, pk):
        try:
            return Booking.objects.get(pk=pk)
        except Booking.DoesNotExist:
            return None

    @extend_schema(
        tags=["bookings"],
        summary="Детали бронирования",
        responses={
            200: BookingListSerializer,
            404: OpenApiResponse(description="Бронирование не найдено"),
        },
    )
    def get(self, request, pk):
        booking = self._get_booking(pk)
        if not booking:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BookingListSerializer(booking).data)

    @extend_schema(
        tags=["bookings"],
        summary="Обновить статус бронирования",
        description="Менеджер меняет статус: `pending` → `confirmed` или `cancelled`.",
        request=BookingStatusUpdateSerializer,
        responses={
            200: BookingListSerializer,
            400: OpenApiResponse(description="Недопустимый статус"),
            404: OpenApiResponse(description="Бронирование не найдено"),
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
        responses={
            204: OpenApiResponse(description="Удалено"),
            404: OpenApiResponse(description="Не найдено"),
        },
    )
    def delete(self, request, pk):
        booking = self._get_booking(pk)
        if not booking:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        booking.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BookingStatsView(APIView):
    """
    Статистика для дашборда — количество по статусам.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["bookings"],
        summary="Статистика бронирований",
        description="Возвращает количество бронирований по каждому статусу + общее количество.",
        responses={200: BookingStatsSerializer},
    )
    def get(self, request):
        qs = Booking.objects.all()
        data = {
            "total":     qs.count(),
            "pending":   qs.filter(status=Booking.Status.PENDING).count(),
            "confirmed": qs.filter(status=Booking.Status.CONFIRMED).count(),
            "cancelled": qs.filter(status=Booking.Status.CANCELLED).count(),
        }
        return Response(data)
