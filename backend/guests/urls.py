from django.urls import path

from . import views

urlpatterns = [
    path("", views.Guests.as_view(), name="guests"),
    path("<int:pk>/", views.guest_detail, name="guest"),
    path("<int:pk>/points/", views.adjust_points, name="guest-points"),
    path("reservations/", views.Reservations.as_view(), name="reservations"),
    path("reservations/<int:pk>/<str:action>/", views.reservation_action, name="reservation-action"),
    path("waitlist/", views.Waitlist.as_view(), name="waitlist"),
    path("waitlist/<int:pk>/<str:action>/", views.waitlist_action, name="waitlist-action"),
]
