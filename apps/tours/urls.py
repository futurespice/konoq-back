from django.urls import path
from .views import TourPublicListView, TourListView, TourDetailView

urlpatterns = [
    path("public/",   TourPublicListView.as_view(), name="tour-public"),   # GET  /api/tours/public/ — без авторизации
    path("",          TourListView.as_view(),        name="tour-list"),     # GET/POST /api/tours/
    path("<int:pk>/", TourDetailView.as_view(),      name="tour-detail"),   # GET/PATCH/DELETE /api/tours/1/
]
