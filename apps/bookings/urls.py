"""
apps/bookings/urls.py
"""
from django.urls import path
from .views import BookingCreateView, BookingListView, BookingDetailView, BookingStatsView

urlpatterns = [
    path("",          BookingListView.as_view(),   name="booking-list"),    # GET  /api/bookings/
    path("create/",   BookingCreateView.as_view(),  name="booking-create"),  # POST /api/bookings/create/
    path("stats/",    BookingStatsView.as_view(),   name="booking-stats"),   # GET  /api/bookings/stats/
    path("<int:pk>/", BookingDetailView.as_view(),  name="booking-detail"),  # GET/PATCH/DELETE /api/bookings/1/
]
