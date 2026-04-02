"""
apps/rooms/views.py
"""
from datetime import date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from .models import Branch, Room
from .serializers import (
    BranchSerializer,
    RoomSerializer,
    RoomAvailabilitySerializer,
    RoomWriteSerializer,
)
from apps.bookings.models import Booking


from django.db.models import Sum

def _get_booked_guests(checkin: date, checkout: date, branch_id=None) -> dict:
    """
    Возвращает dict {room_type: sum_of_guests} в указанный период.
    """
    qs = Booking.objects.filter(
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
        checkin__lt=checkout,
        checkout__gt=checkin,
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    aggs = qs.values("room").annotate(total_guests=Sum("guests"))
    return {row["room"]: row["total_guests"] for row in aggs}


# ── Branch ────────────────────────────────────────────────────────────────────

class BranchListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["rooms"], summary="Список филиалов", responses={200: BranchSerializer(many=True)})
    def get(self, request):
        return Response(BranchSerializer(Branch.objects.filter(is_active=True), many=True).data)

    @extend_schema(tags=["rooms"], summary="Добавить филиал", request=BranchSerializer, responses={201: BranchSerializer})
    def post(self, request):
        ser = BranchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=status.HTTP_201_CREATED)


class BranchDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return Branch.objects.get(pk=pk)
        except Branch.DoesNotExist:
            return None

    @extend_schema(tags=["rooms"], summary="Детали филиала", responses={200: BranchSerializer})
    def get(self, request, pk):
        branch = self._get(pk)
        if not branch:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BranchSerializer(branch).data)

    @extend_schema(tags=["rooms"], summary="Обновить филиал", request=BranchSerializer, responses={200: BranchSerializer})
    def patch(self, request, pk):
        branch = self._get(pk)
        if not branch:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        ser = BranchSerializer(branch, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    @extend_schema(tags=["rooms"], summary="Удалить филиал", responses={204: None})
    def delete(self, request, pk):
        branch = self._get(pk)
        if not branch:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        branch.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Room ──────────────────────────────────────────────────────────────────────

class RoomListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["rooms"],
        summary="Список всех номеров",
        parameters=[
            OpenApiParameter("branch",   OpenApiTypes.INT,  description="Фильтр по филиалу (id)"),
            OpenApiParameter("checkin",  OpenApiTypes.DATE, description="Дата заезда для проверки свободности"),
            OpenApiParameter("checkout", OpenApiTypes.DATE, description="Дата выезда для проверки свободности"),
        ],
        responses={200: RoomAvailabilitySerializer(many=True)},
    )
    def get(self, request):
        rooms = Room.objects.filter(is_active=True).select_related("branch")
        branch_id = request.query_params.get("branch")
        if branch_id:
            rooms = rooms.filter(branch_id=branch_id)

        checkin_str  = request.query_params.get("checkin")
        checkout_str = request.query_params.get("checkout")

        if checkin_str and checkout_str:
            try:
                checkin  = date.fromisoformat(checkin_str)
                checkout = date.fromisoformat(checkout_str)
                booked_guests_by_type = _get_booked_guests(checkin, checkout, branch_id)
                
                capacity_by_type = {}
                for room in rooms:
                    capacity_by_type[room.room_type] = capacity_by_type.get(room.room_type, 0) + room.capacity

                data = []
                for room in rooms:
                    d = RoomSerializer(room).data
                    booked = booked_guests_by_type.get(room.room_type, 0)
                    cap = capacity_by_type.get(room.room_type, 0)
                    d["is_available"] = booked < cap
                    data.append(d)
                return Response(data)
            except ValueError:
                pass

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
            return Room.objects.select_related("branch").get(pk=pk)
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
