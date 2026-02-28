"""
apps/users/urls.py
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.utils import extend_schema

from .views import LoginView, LogoutView, MeView, ChangePasswordView

# Декорируем стандартный view simplejwt для красивого Swagger
TokenRefreshView = extend_schema(
    tags=["auth"],
    summary="Обновить access-токен",
    description="Принимает refresh-токен, возвращает новый access-токен (и новый refresh при ROTATE=True).",
)(TokenRefreshView)

urlpatterns = [
    path("login/",           LoginView.as_view(),          name="auth-login"),
    path("logout/",          LogoutView.as_view(),          name="auth-logout"),
    path("me/",              MeView.as_view(),              name="auth-me"),
    path("token/refresh/",   TokenRefreshView.as_view(),    name="auth-token-refresh"),
    path("change-password/", ChangePasswordView.as_view(),  name="auth-change-password"),
]
