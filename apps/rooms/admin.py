from django.contrib import admin
from .models import Room

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display  = ["number", "room_type", "capacity", "price_per_night", "is_active"]
    list_editable = ["price_per_night", "is_active"]
    list_filter   = ["room_type", "is_active"]
