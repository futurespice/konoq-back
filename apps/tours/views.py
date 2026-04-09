"""
apps/tours/views.py
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Tour
from .serializers import TourSerializer


class TourPublicListView(APIView):
    """
    Публичный эндпоинт — список активных туров для главной страницы.
    Авторизация НЕ нужна.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["tours"],
        summary="Публичный список туров",
        description="Возвращает только активные туры (is_active=True). Авторизация не нужна.",
        responses={200: TourSerializer(many=True)},
    )
    def get(self, request):
        tours = Tour.objects.filter(is_active=True)
        return Response(TourSerializer(tours, many=True).data)


class TourListView(APIView):
    """
    Полный список туров + создание — только для авторизованных.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["tours"], summary="Список всех туров (менеджер)", responses={200: TourSerializer(many=True)})
    def get(self, request):
        tours = Tour.objects.all()
        return Response(TourSerializer(tours, many=True).data)

    @extend_schema(
        tags=["tours"], summary="Добавить тур",
        request=TourSerializer,
        responses={201: TourSerializer, 400: OpenApiResponse(description="Ошибка валидации")},
    )
    def post(self, request):
        ser = TourSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tour = ser.save()
        return Response(TourSerializer(tour).data, status=status.HTTP_201_CREATED)


class TourDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def _get(self, pk):
        try:
            return Tour.objects.get(pk=pk)
        except Tour.DoesNotExist:
            return None

    @extend_schema(tags=["tours"], summary="Детали тура", responses={200: TourSerializer})
    def get(self, request, pk):
        tour = self._get(pk)
        if not tour:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TourSerializer(tour).data)

    @extend_schema(tags=["tours"], summary="Редактировать тур", request=TourSerializer, responses={200: TourSerializer})
    def patch(self, request, pk):
        tour = self._get(pk)
        if not tour:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        ser = TourSerializer(tour, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(TourSerializer(tour).data)

    @extend_schema(tags=["tours"], summary="Удалить тур", responses={204: None})
    def delete(self, request, pk):
        tour = self._get(pk)
        if not tour:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        tour.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
