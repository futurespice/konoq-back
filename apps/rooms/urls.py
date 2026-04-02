from django.urls import path
from .views import BranchListView, BranchDetailView, RoomListView, RoomDetailView

urlpatterns = [
    path("branches/",         BranchListView.as_view(),   name="branch-list"),
    path("branches/<int:pk>/", BranchDetailView.as_view(), name="branch-detail"),
    path("",                  RoomListView.as_view(),     name="room-list"),
    path("<int:pk>/",         RoomDetailView.as_view(),   name="room-detail"),
]
