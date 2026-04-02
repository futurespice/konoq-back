"""
apps/bookings/admin.py
"""
from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "id", "name", "surname", "phone",
        "checkin", "checkout", "get_nights",
        "guests", "room", "branch", "source",
        "country", "purpose", "status", "created_at",
    ]
    list_filter   = ["status", "room", "source", "branch", "purpose", "country"]
    search_fields = ["name", "surname", "phone", "email", "country"]
    ordering      = ["-created_at"]
    list_editable  = ["status"]
    readonly_fields = ["created_at", "updated_at", "get_nights"]

    fieldsets = (
        ("Гость", {
            "fields": ("name", "surname", "phone", "email")
        }),
        ("Бронирование", {
            "fields": ("checkin", "checkout", "get_nights", "guests", "room", "branch", "comment")
        }),
        ("Анкета", {
            "fields": ("country", "purpose")
        }),
        ("Канал и управление", {
            "fields": ("source", "status", "created_at", "updated_at")
        }),
    )

    @admin.display(description="Ночей")
    def get_nights(self, obj):
        return obj.nights
