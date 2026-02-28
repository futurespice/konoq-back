from django.contrib import admin
from .models import Tour

@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display  = ["name", "price", "duration_hours", "meeting_point", "is_active"]
    list_editable = ["price", "is_active"]
    search_fields = ["name", "description"]
