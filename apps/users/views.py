"""
apps/users/views.py
"""
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse

from .models import User
from .serializers import (
    LoginSerializer,
    LoginResponseSerializer,
    UserSerializer,
    ChangePasswordSerializer,
    LogoutSerializer,
    MessageResponseSerializer,
)


def _token_response(user):
    """Формирует словарь с токенами и данными пользователя."""
    refresh = RefreshToken.for_user(user)
    return {
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
        "user":    UserSerializer(user).data,
    }


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary="Вход в систему",
        description="Принимает логин и пароль, возвращает JWT access/refresh токены и данные пользователя.",
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            401: OpenApiResponse(description="Неверный логин или пароль"),
            403: OpenApiResponse(description="Аккаунт отключён"),
        },
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={"username": "manager", "password": "manager123"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response(
                {"detail": "Неверный логин или пароль."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"detail": "Аккаунт отключён. Обратитесь к администратору."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(_token_response(user), status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Выход из системы",
        description="Инвалидирует refresh-токен (добавляет в чёрный список). Access-токен истечёт сам.",
        request=LogoutSerializer,
        responses={
            200: MessageResponseSerializer,
            400: OpenApiResponse(description="Refresh-токен не передан или недействителен"),
        },
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Токен недействителен или уже использован."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"detail": "Выход выполнен."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Текущий пользователь",
        description="Возвращает данные авторизованного пользователя по Bearer-токену.",
        responses={200: UserSerializer},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Смена пароля",
        description="Меняет пароль текущего пользователя. Требует подтверждения старого пароля.",
        request=ChangePasswordSerializer,
        responses={
            200: MessageResponseSerializer,
            400: OpenApiResponse(description="Неверный текущий пароль или пароли не совпадают"),
        },
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"old_password": "Неверный текущий пароль."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Пароль успешно изменён."})
