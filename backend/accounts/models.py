from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    COOK = "cook", "Cook"
    MANAGER = "manager", "Manager"
    OWNER = "owner", "Owner"


# Plain string keys on purpose: role values are stored as strings.
ROLE_RANK = {"cook": 0, "manager": 1, "owner": 2}


class User(AbstractUser):
    """A staff member. Owners see every location; others only the ones assigned to them."""

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.COOK)
    locations = models.ManyToManyField("catalog.Location", blank=True, related_name="staff")

    def has_role(self, role: str) -> bool:
        if self.is_superuser:
            return True
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK[role]

    def location_ids(self) -> set[int]:
        from catalog.models import Location

        if self.is_superuser or self.role == Role.OWNER:
            return set(Location.objects.values_list("id", flat=True))
        return set(self.locations.values_list("id", flat=True))

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username
