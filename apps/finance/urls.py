"""
apps/finance/urls.py
"""
from django.urls import path
from .views import (
    FinanceSummaryView,
    RevenueTargetView,
    BySourceView,
    ByBranchView,
    OccupancyView,
)

urlpatterns = [
    path("summary/",   FinanceSummaryView.as_view(), name="finance-summary"),
    path("targets/",   RevenueTargetView.as_view(),  name="finance-targets"),
    path("by-source/", BySourceView.as_view(),       name="finance-by-source"),
    path("by-branch/", ByBranchView.as_view(),       name="finance-by-branch"),
    path("occupancy/", OccupancyView.as_view(),      name="finance-occupancy"),
]
