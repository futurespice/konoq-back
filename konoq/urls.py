"""
konoq/urls.py — корневой роутер
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # API
    path("api/auth/",     include("apps.users.urls")),
    path("api/bookings/", include("apps.bookings.urls")),
    path("api/rooms/",    include("apps.rooms.urls")),
    path("api/tours/",    include("apps.tours.urls")),
    path("api/finance/",  include("apps.finance.urls")),

    # Telegram Bot webhook
    path("api/tg/", include("apps.tg_bot.urls")),

    # WhatsApp Bot webhook
    path("api/wa/", include("apps.wa_bot.urls")),

    # Schema & Docs
    path("api/schema/", SpectacularAPIView.as_view(),                         name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"),    name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),      name="redoc"),
]
