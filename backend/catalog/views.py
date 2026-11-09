from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsManager, IsOwner
from audit.services import log

from .models import Item, Location, MenuItem, MenuLine, RecipeLine, Vendor
from .serializers import (
    ItemSerializer, LocationSerializer, MenuItemSerializer, PriceHistorySerializer,
    RecipeInSerializer, VendorSerializer,
)

READ_ACTIONS = ("list", "retrieve")


def _money(x):
    return f"${x:,.2f}"


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LocationSerializer

    def get_queryset(self):
        return Location.objects.filter(id__in=self.request.user.location_ids())


class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer
    queryset = Vendor.objects.all()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        return [IsAuthenticated()] if self.action in READ_ACTIONS else [IsManager()]

    def perform_create(self, serializer):
        vendor = serializer.save()
        log(self.request.user, "Added vendor", vendor.name)

    def perform_update(self, serializer):
        vendor = serializer.save()
        log(self.request.user, "Updated vendor", vendor.name)


class ItemViewSet(viewsets.ModelViewSet):
    """Stock items. Everyone can read; only owners change items and recipes."""

    serializer_class = ItemSerializer
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_queryset(self):
        qs = Item.objects.select_related("vendor")
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        if self.request.query_params.get("active") != "all":
            qs = qs.filter(is_active=True)
        return qs

    def get_permissions(self):
        if self.action in READ_ACTIONS or self.action == "price_history":
            return [IsAuthenticated()]
        return [IsOwner()]

    def perform_create(self, serializer):
        item = serializer.save()
        log(self.request.user, "Added item", f"{item.name} ({item.get_kind_display()}, {item.unit})")

    def perform_update(self, serializer):
        before = {k: getattr(serializer.instance, k) for k in serializer.validated_data}
        item = serializer.save()
        changes = [f"{k} {before[k]} → {getattr(item, k)}" for k in before if before[k] != getattr(item, k)]
        log(self.request.user, "Updated item", f"{item.name}: {', '.join(changes) or 'no change'}")

    @action(detail=True, methods=["put"])
    def recipe(self, request, pk=None):
        """Replace a prep's recipe. Body: {"lines": [{"item": id, "qty": number}, ...]}"""
        prep = self.get_object()
        if prep.kind != Item.Kind.PREP:
            raise ValidationError({"detail": "Only prep items have recipes."})
        data = RecipeInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if any(line["item"].id == prep.id for line in data.validated_data["lines"]):
            raise ValidationError({"detail": "A prep can't contain itself."})
        old_cost = prep.unit_cost()
        with transaction.atomic():
            prep.recipe_lines.all().delete()
            RecipeLine.objects.bulk_create(
                RecipeLine(prep=prep, component=line["item"], qty=line["qty"]) for line in data.validated_data["lines"]
            )
        log(request.user, "Changed prep recipe",
            f"{prep.name}: cost per {prep.unit} {_money(old_cost)} → {_money(prep.unit_cost())}")
        return Response(ItemSerializer(prep).data)

    @action(detail=True, methods=["get"], url_path="price-history")
    def price_history(self, request, pk=None):
        item = self.get_object()
        return Response(PriceHistorySerializer(item.price_history.all()[:26], many=True).data)


class MenuItemViewSet(viewsets.ModelViewSet):
    """Dishes with live plate cost. Managers can see costs; only owners change recipes or prices."""

    serializer_class = MenuItemSerializer
    queryset = MenuItem.objects.all()
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_permissions(self):
        return [IsManager()] if self.action in READ_ACTIONS else [IsOwner()]

    def perform_create(self, serializer):
        dish = serializer.save()
        log(self.request.user, "Added dish", f"{dish.name} at {_money(dish.price)}")

    def perform_update(self, serializer):
        old_price = serializer.instance.price
        dish = serializer.save()
        if dish.price != old_price:
            log(self.request.user, "Changed menu price", f"{dish.name} {_money(old_price)} → {_money(dish.price)}")
        else:
            log(self.request.user, "Updated dish", dish.name)

    @action(detail=True, methods=["put"])
    def recipe(self, request, pk=None):
        """Replace a dish's ingredients (and optionally its price) in one go."""
        dish = self.get_object()
        data = RecipeInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        old_cost, old_price = dish.plate_cost(), dish.price
        with transaction.atomic():
            dish.lines.all().delete()
            MenuLine.objects.bulk_create(
                MenuLine(menu_item=dish, item=line["item"], qty=line["qty"]) for line in data.validated_data["lines"]
            )
            if "price" in data.validated_data:
                dish.price = data.validated_data["price"]
                dish.save(update_fields=["price"])
        detail = f"{dish.name}: plate cost {_money(old_cost)} → {_money(dish.plate_cost())}"
        if dish.price != old_price:
            detail += f", price {_money(old_price)} → {_money(dish.price)}"
        log(request.user, "Changed dish recipe", detail)
        return Response(MenuItemSerializer(dish).data)
