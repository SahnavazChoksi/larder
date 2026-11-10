from rest_framework.routers import DefaultRouter

from .views import ItemViewSet, LocationViewSet, MenuCategoryViewSet, MenuItemViewSet, ModifierGroupViewSet, VendorViewSet

router = DefaultRouter()
router.register("locations", LocationViewSet, basename="location")
router.register("vendors", VendorViewSet, basename="vendor")
router.register("items", ItemViewSet, basename="item")
router.register("menu-items", MenuItemViewSet, basename="menu-item")
router.register("menu-categories", MenuCategoryViewSet, basename="menu-category")
router.register("modifier-groups", ModifierGroupViewSet, basename="modifier-group")

urlpatterns = router.urls
