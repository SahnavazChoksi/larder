from rest_framework import serializers

from catalog.models import Location

from .models import User


class LocationBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name", "city", "kind", "brand"]


class MeSerializer(serializers.ModelSerializer):
    locations = serializers.SerializerMethodField()
    kitchens = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "display_name", "role", "locations", "kitchens"]

    def get_kitchens(self, user):
        """Kitchens anyone can request prep from, even without working there."""
        return LocationBriefSerializer(Location.objects.filter(kind=Location.Kind.KITCHEN), many=True).data

    def get_locations(self, user):
        qs = Location.objects.filter(id__in=user.location_ids()).order_by("kind", "name")
        return LocationBriefSerializer(qs, many=True).data


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8, allow_blank=False)
    location_names = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "role",
            "locations", "location_names", "is_active", "last_login", "password",
        ]
        read_only_fields = ["last_login"]

    def get_location_names(self, user):
        if user.role == "owner":
            return ["All locations"]
        return [loc.name for loc in user.locations.all()]

    def create(self, validated):
        password = validated.pop("password", None)
        locations = validated.pop("locations", [])
        user = User(**validated)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        user.locations.set(locations)
        return user

    def update(self, instance, validated):
        password = validated.pop("password", None)
        locations = validated.pop("locations", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        if locations is not None:
            instance.locations.set(locations)
        return instance
