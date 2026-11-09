from django.urls import path

from . import views

urlpatterns = [
    path("variance/", views.variance, name="report-variance"),
    path("dashboard/", views.dashboard, name="report-dashboard"),
]
