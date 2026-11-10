from django.urls import path

from . import views

urlpatterns = [
    path("variance/", views.variance, name="report-variance"),
    path("dashboard/", views.dashboard, name="report-dashboard"),
    path("performance/", views.performance, name="report-performance"),
    path("menu-engineering/", views.menu_engineering, name="report-menu-engineering"),
    path("forecast/", views.forecast, name="report-forecast"),
    path("service-times/", views.service_times, name="report-service-times"),
    path("accounting-export/", views.accounting_export, name="report-accounting-export"),
]
