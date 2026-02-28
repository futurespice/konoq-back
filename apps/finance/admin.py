from django.contrib import admin
from .models import RevenueTarget

@admin.register(RevenueTarget)
class RevenueTargetAdmin(admin.ModelAdmin):
    list_display = ["year", "month", "target", "note"]
    ordering     = ["-year", "-month"]
