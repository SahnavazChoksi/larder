from rest_framework.routers import DefaultRouter

from .views import ItemViewSet, LocationViewSet, MenuItemViewSet, VendorViewSet

router = DefaultRouter()
router.register("locations", LocationViewSet, basename="location")
router.register("vendors", VendorViewSet, basename="vendor")
router.register("items", ItemViewSet, basename="item")
router.register("menu-items", MenuItemViewSet, basename="menu-item")

urlpatterns = router.urls
