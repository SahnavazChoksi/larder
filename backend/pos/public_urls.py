from django.urls import path

from . import views

urlpatterns = [
    path("menu/<str:code>/", views.public_menu, name="public-menu"),
    path("orders/<str:code>/", views.public_order, name="public-order"),
    path("order-status/<uuid:token>/", views.public_status, name="public-order-status"),
]
