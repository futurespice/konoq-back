"""
apps/bookings/urls.py
"""
from django.urls import path
from .views import BookingCreateView, BookingListView, BookingDetailView, BookingStatsView
from .ical_views import ICalLinkListView, ICalLinkDetailView, ICalExportView, ICalSyncView

urlpatterns = [
    path("",          BookingListView.as_view(),   name="booking-list"),    # GET  /api/bookings/
    path("create/",   BookingCreateView.as_view(),  name="booking-create"),  # POST /api/bookings/create/
    path("stats/",    BookingStatsView.as_view(),   name="booking-stats"),   # GET  /api/bookings/stats/
    path("<int:pk>/", BookingDetailView.as_view(),  name="booking-detail"),  # GET/PATCH/DELETE /api/bookings/1/
    
    # iCal
    path("ical/links/", ICalLinkListView.as_view(), name="ical-link-list"),
    path("ical/links/<int:pk>/", ICalLinkDetailView.as_view(), name="ical-link-detail"),
    path("ical/export/<int:branch_id>/<str:room_type>/", ICalExportView.as_view(), name="ical-export"),
    path("ical/sync/", ICalSyncView.as_view(), name="ical-sync"),
]
