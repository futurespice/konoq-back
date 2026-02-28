"""
apps/users/serializers.py
"""
from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Данные пользователя (read-only)."""
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model  = User
        fields = ["id", "username", "email", "first_name", "last_name",
                  "role", "role_display", "phone", "is_active", "date_joined"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """Тело запроса для входа."""
    username = serializers.CharField(
        max_length=150,
        help_text="Логин пользователя",
    )
    password = serializers.CharField(
        write_only=True,
        help_text="Пароль",
    )


class LoginResponseSerializer(serializers.Serializer):
    """Тело ответа на успешный вход — только для Swagger-документации."""
    access  = serializers.CharField(help_text="JWT Access-токен (живёт 8 ч)")
    refresh = serializers.CharField(help_text="JWT Refresh-токен (живёт 30 дней)")
    user    = UserSerializer()


class LogoutSerializer(serializers.Serializer):
    """Тело запроса для выхода."""
    refresh = serializers.CharField(help_text="Refresh-токен для инвалидации")


class ChangePasswordSerializer(serializers.Serializer):
    """Смена пароля текущим пользователем."""
    old_password        = serializers.CharField(write_only=True, help_text="Текущий пароль")
    new_password        = serializers.CharField(write_only=True, min_length=8,
                                                help_text="Новый пароль (мин. 8 символов)")
    new_password_confirm = serializers.CharField(write_only=True, help_text="Подтверждение нового пароля")

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Пароли не совпадают."}
            )
        return attrs


class MessageResponseSerializer(serializers.Serializer):
    """Простой ответ с сообщением — для Swagger."""
    detail = serializers.CharField(help_text="Текст сообщения")
