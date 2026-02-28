from django.urls import path
from .views import TourListView, TourDetailView

urlpatterns = [
    path("",         TourListView.as_view(),   name="tour-list"),
    path("<int:pk>/", TourDetailView.as_view(), name="tour-detail"),
]
