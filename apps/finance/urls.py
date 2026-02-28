from django.urls import path
from .views import FinanceSummaryView, RevenueTargetView

urlpatterns = [
    path("summary/", FinanceSummaryView.as_view(), name="finance-summary"),
    path("targets/", RevenueTargetView.as_view(),  name="finance-targets"),
]
