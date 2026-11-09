from django.urls import path

from . import views

urlpatterns = [
    path("days/", views.days, name="sales-days"),
    path("items/", views.item_sales, name="sales-items"),
    path("import/", views.import_csv, name="sales-import"),
]
