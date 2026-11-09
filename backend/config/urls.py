from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("catalog.urls")),
    path("api/stock/", include("stock.urls")),
    path("api/purchasing/", include("purchasing.urls")),
    path("api/sales/", include("sales.urls")),
    path("api/reports/", include("reports.urls")),
    path("api/audit/", include("audit.urls")),
]
