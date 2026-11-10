from django.urls import path

from . import views

urlpatterns = [
    path("menu/", views.menu, name="pos-menu"),
    path("ping/", views.ping, name="pos-ping"),
    path("offline-kit/", views.offline_kit, name="pos-offline-kit"),
    path("offline-orders/", views.offline_orders, name="pos-offline-orders"),
    path("floor/", views.floor, name="pos-floor"),
    path("tables/", views.Tables.as_view(), name="pos-tables"),
    path("tables/<int:pk>/", views.table_detail, name="pos-table"),
    path("orders/", views.Orders.as_view(), name="pos-orders"),
    path("orders/<int:pk>/", views.order_detail, name="pos-order"),
    path("orders/<int:pk>/lines/", views.add_line, name="pos-add-line"),
    path("orders/<int:pk>/lines/<int:line_id>/", views.change_line, name="pos-change-line"),
    path("orders/<int:pk>/lines/<int:line_id>/void/", views.void_line, name="pos-void-line"),
    path("orders/<int:pk>/send/", views.send, name="pos-send"),
    path("orders/<int:pk>/service-charge/", views.service_charge, name="pos-sc"),
    path("orders/<int:pk>/discount/", views.discount, name="pos-discount"),
    path("orders/<int:pk>/redeem/", views.redeem, name="pos-redeem"),
    path("orders/<int:pk>/payments/", views.pay, name="pos-pay"),
    path("orders/<int:pk>/close/", views.close, name="pos-close"),
    path("orders/<int:pk>/void/", views.void, name="pos-void"),
    path("payments/<int:pk>/refund/", views.refund, name="pos-refund"),
    path("providers/", views.provider_list, name="pos-providers"),
    path("payments/webhook/<str:provider>/", views.payment_webhook, name="pos-payment-webhook"),
    path("integrations/<str:platform>/orders/", views.integration_order, name="pos-integration-order"),
    path("kds/", views.kds, name="pos-kds"),
    path("tickets/<int:pk>/<str:step>/", views.ticket_step, name="pos-ticket-step"),
]
