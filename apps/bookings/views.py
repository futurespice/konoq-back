"""
apps/bookings/views.py

Только HTTP-каркас: парсинг query params, вызов сериализаторов, вызов
services/selectors, формирование Response. Бизнес-логика и работа с БД —
в services.py / selectors.py.
"""
from datetime import date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import (
    extend_schema, OpenApiResponse, OpenApiParameter, OpenApiExample
)
from drf_spectacular.types import OpenApiTypes

from apps.rooms.models import Bed

from .models import Booking
from .selectors import (
    get_availability_summary,
    get_booking_by_id,
    get_booking_stats,
    list_bookings,
)
from .serializers import (
    BookingCreateSerializer,
    BookingListSerializer,
    BookingPreviewSerializer,
    BookingStatusUpdateSerializer,
    BookingStatsSerializer,
    BookingV2CreateSerializer,
    BookingV2OutSerializer,
)
from .services import (
    auto_assign_beds,
    calculate_booking_total,
    create_booking_with_beds,
    delete_booking,
    notify_new_booking,
    update_booking_status,
)


class BookingCreateView(APIView):
    """Публичный эндпоинт — гость отправляет форму бронирования."""
    authentication_classes = []  # Не аутентифицируем — иначе просроченный токен в localStorage вызовет 401
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

        notify_new_booking(booking)

        return Response(
            BookingListSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


class BookingListView(APIView):
    """Список всех бронирований — только для авторизованных менеджеров."""
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
        qs = list_bookings(
            status=request.query_params.get("status"),
            source=request.query_params.get("source"),
            branch_id=request.query_params.get("branch"),
            search=request.query_params.get("search"),
            checkin_from=request.query_params.get("checkin"),
        )
        return Response(BookingListSerializer(qs, many=True).data)


class BookingDetailView(APIView):
    """Получить / обновить статус / удалить одно бронирование."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["bookings"],
        summary="Детали бронирования",
        responses={200: BookingListSerializer, 404: OpenApiResponse(description="Не найдено")},
    )
    def get(self, request, pk):
        booking = get_booking_by_id(pk=pk)
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
        serializer = BookingStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking = update_booking_status(
                booking_id=pk,
                new_status=serializer.validated_data["status"],
            )
        except Booking.DoesNotExist:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BookingListSerializer(booking).data)

    @extend_schema(
        tags=["bookings"],
        summary="Удалить бронирование",
        responses={204: OpenApiResponse(description="Удалено"), 404: OpenApiResponse(description="Не найдено")},
    )
    def delete(self, request, pk):
        if not delete_booking(booking_id=pk):
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
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
        data = get_booking_stats(branch_id=request.query_params.get("branch"))
        return Response(data)


# ── Bed-level API v2 (Этап 2b) ───────────────────────────────────────────────

class AvailabilityView(APIView):
    """GET /api/availability/?branch=<id>&checkin=YYYY-MM-DD&checkout=YYYY-MM-DD"""
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["bookings"],
        summary="Сводка свободных шконок по типам номеров",
        parameters=[
            OpenApiParameter("branch", OpenApiTypes.INT, required=True),
            OpenApiParameter("checkin", OpenApiTypes.DATE, required=True),
            OpenApiParameter("checkout", OpenApiTypes.DATE, required=True),
        ],
        responses={200: OpenApiResponse(description="Список options по room_type")},
    )
    def get(self, request):
        try:
            branch_id = int(request.query_params.get("branch", ""))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Параметр branch обязателен и должен быть числом."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            checkin = date.fromisoformat(request.query_params.get("checkin", ""))
            checkout = date.fromisoformat(request.query_params.get("checkout", ""))
        except ValueError:
            return Response(
                {"detail": "checkin и checkout должны быть в формате YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if checkin >= checkout:
            return Response(
                {"detail": "checkout должен быть позже checkin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = get_availability_summary(
            branch_id=branch_id, checkin=checkin, checkout=checkout,
        )
        return Response(data)


class BookingV2PreviewView(APIView):
    """POST /api/bookings/v2/preview/ — автоподбор без создания."""
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["bookings"],
        summary="Preview автоподбора шконок",
        request=BookingPreviewSerializer,
        responses={
            200: OpenApiResponse(description="Список beds + total_price + nights"),
            400: OpenApiResponse(description="Нет свободных мест или ошибка валидации"),
        },
    )
    def post(self, request):
        serializer = BookingPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        beds = auto_assign_beds(
            branch_id=vd["branch"].id,
            room_type=vd["room_type"],
            checkin=vd["checkin"],
            checkout=vd["checkout"],
            guests=vd["guests"],
            want_private_room=vd.get("want_private_room", False),
        )

        nights = (vd["checkout"] - vd["checkin"]).days
        total = calculate_booking_total(beds=beds, nights=nights)

        return Response({
            "beds": [
                {
                    "id": b.id,
                    "room_number": b.room.number,
                    "room_type": b.room.room_type,
                    "label": b.label,
                }
                for b in beds
            ],
            "total_price": total,
            "nights": nights,
            "can_confirm": True,
        })


class BookingV2CreateView(APIView):
    """POST /api/bookings/v2/ — создание брони с привязкой к конкретным шконкам."""
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["bookings"],
        summary="Создать бронирование (bed-level)",
        request=BookingV2CreateSerializer,
        responses={
            201: BookingV2OutSerializer,
            400: OpenApiResponse(description="Ошибка валидации или нет мест"),
        },
    )
    def post(self, request):
        serializer = BookingV2CreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        branch = vd["branch"]

        if vd.get("bed_ids"):
            beds = vd["_beds"]
            is_private = False
        else:
            beds = auto_assign_beds(
                branch_id=branch.id,
                room_type=vd["room_type"],
                checkin=vd["checkin"],
                checkout=vd["checkout"],
                guests=vd["guests"],
                want_private_room=vd.get("want_private_room", False),
            )
            is_private = vd.get("want_private_room", False)

        booking = create_booking_with_beds(
            branch_id=branch.id,
            beds=beds,
            checkin=vd["checkin"],
            checkout=vd["checkout"],
            is_private_booking=is_private,
            name=vd["name"],
            surname=vd.get("surname", ""),
            phone=vd["phone"],
            email=vd.get("email", ""),
            country=vd["country"],
            purpose=vd.get("purpose", Booking.Purpose.OTHER),
            comment=vd.get("comment", ""),
            source=vd.get("source", Booking.Source.DIRECT),
        )

        notify_new_booking(booking)

        return Response(
            BookingV2OutSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )
