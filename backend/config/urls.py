from django.conf import settings
from django.conf.urls.static import static
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
    path("api/checklists/", include("checklists.urls")),
    path("api/ops/", include("ops.urls")),
    path("api/pos/", include("pos.urls")),
    path("api/guests/", include("guests.urls")),
    path("api/public/", include("pos.public_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
