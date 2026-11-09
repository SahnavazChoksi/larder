from django.urls import path

from . import views

urlpatterns = [
    path("levels/", views.levels, name="stock-levels"),
    path("pars/", views.set_pars, name="stock-pars"),
    path("movements/", views.MovementList.as_view(), name="stock-movements"),
    path("counts/", views.Counts.as_view(), name="stock-counts"),
    path("wastage/", views.WastageView.as_view(), name="stock-wastage"),
    path("transfers/", views.Transfers.as_view(), name="transfers"),
    path("transfers/<int:pk>/dispatch/", views.dispatch_transfer, name="transfer-dispatch"),
    path("transfers/<int:pk>/receive/", views.receive_transfer, name="transfer-receive"),
    path("transfers/<int:pk>/cancel/", views.cancel_transfer, name="transfer-cancel"),
    path("batches/", views.Batches.as_view(), name="batches"),
    path("batches/<int:pk>/", views.batch_detail, name="batch-detail"),
    path("batches/<int:pk>/complete/", views.complete_batch, name="batch-complete"),
]
