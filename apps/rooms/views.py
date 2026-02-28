"""
apps/rooms/views.py
"""
from datetime import date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from .models import Room
from .serializers import RoomSerializer, RoomAvailabilitySerializer, RoomWriteSerializer
from apps.bookings.models import Booking


def _get_booked_types(checkin: date, checkout: date) -> set:
    """
    Возвращает типы номеров, занятых в указанный период.
    Бронирование пересекается, если: checkin < booking.checkout AND checkout > booking.checkin
    """
    overlapping = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        checkin__lt=checkout,
        checkout__gt=checkin,
    ).values_list("room", flat=True)
    return set(overlapping)


class RoomListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["rooms"],
        summary="Список всех номеров",
        parameters=[
            OpenApiParameter("checkin",  OpenApiTypes.DATE, description="Дата заезда для проверки свободности"),
            OpenApiParameter("checkout", OpenApiTypes.DATE, description="Дата выезда для проверки свободности"),
        ],
        responses={200: RoomAvailabilitySerializer(many=True)},
    )
    def get(self, request):
        rooms = Room.objects.filter(is_active=True)
        checkin_str  = request.query_params.get("checkin")
        checkout_str = request.query_params.get("checkout")

        if checkin_str and checkout_str:
            try:
                checkin  = date.fromisoformat(checkin_str)
                checkout = date.fromisoformat(checkout_str)
                booked_types = _get_booked_types(checkin, checkout)
                data = []
                for room in rooms:
                    d = RoomSerializer(room).data
                    d["is_available"] = room.room_type not in booked_types
                    data.append(d)
                return Response(data)
            except ValueError:
                pass

        # Без дат — просто список
        data = [{**RoomSerializer(r).data, "is_available": None} for r in rooms]
        return Response(data)

    @extend_schema(
        tags=["rooms"],
        summary="Добавить номер",
        request=RoomWriteSerializer,
        responses={201: RoomSerializer, 400: OpenApiResponse(description="Ошибка валидации")},
    )
    def post(self, request):
        ser = RoomWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        room = ser.save()
        return Response(RoomSerializer(room).data, status=status.HTTP_201_CREATED)


class RoomDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return Room.objects.get(pk=pk)
        except Room.DoesNotExist:
            return None

    @extend_schema(tags=["rooms"], summary="Детали номера", responses={200: RoomSerializer})
    def get(self, request, pk):
        room = self._get(pk)
        if not room:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(RoomSerializer(room).data)

    @extend_schema(tags=["rooms"], summary="Обновить номер", request=RoomWriteSerializer, responses={200: RoomSerializer})
    def patch(self, request, pk):
        room = self._get(pk)
        if not room:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        ser = RoomWriteSerializer(room, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(RoomSerializer(room).data)

    @extend_schema(tags=["rooms"], summary="Удалить номер", responses={204: None})
    def delete(self, request, pk):
        room = self._get(pk)
        if not room:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        room.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
