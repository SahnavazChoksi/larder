from django.urls import path

from . import views

urlpatterns = [
    path("orders/", views.Orders.as_view(), name="po-list"),
    path("orders/<int:pk>/send/", views.send_order, name="po-send"),
    path("orders/<int:pk>/receive/", views.receive_order, name="po-receive"),
    path("orders/<int:pk>/cancel/", views.cancel_order, name="po-cancel"),
    path("suggestions/", views.Suggestions.as_view(), name="po-suggestions"),
    path("price-moves/", views.price_moves, name="price-moves"),
]
