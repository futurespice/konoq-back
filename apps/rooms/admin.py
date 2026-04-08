"""
apps/rooms/admin.py
"""
from django.contrib import admin
from .models import Branch, Room


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display  = ["name", "address", "is_active"]
    list_editable = ["is_active"]
    search_fields = ["name"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display  = [
        "number", "branch", "room_type", "capacity",
        "price_per_night", "price_is_per_bed", "has_bathroom", "is_active", "image",
    ]
    list_editable = ["price_per_night", "is_active"]
    list_filter   = ["branch", "room_type", "has_bathroom", "is_active"]
    search_fields = ["number", "description"]
