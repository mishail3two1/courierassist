from django.conf import settings
from django.db import models
from geopy.exc import GeopyError
from geopy.geocoders import Nominatim


class OrderStatus(models.TextChoices):
    NEED = "NEED", "Need"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    DELIVERED = "DELIVERED", "Delivered"


class ClusterStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    TAKEN = "TAKEN", "Taken"
    COMPLETED = "COMPLETED", "Completed"


def geocode_chelyabinsk_address(address: str):
    if not address:
        return None

    geolocator = Nominatim(user_agent="courierassist-study-project")

    structured_query = {
        "street": address,
        "city": "Челябинск",
        "county": "Челябинский городской округ",
        "country": "Россия",
    }

    try:
        location = geolocator.geocode(
            query=structured_query,
            exactly_one=True,
            timeout=10,
        )
        if location:
            return location.latitude, location.longitude
    except GeopyError:
        return None

    return None


class Cluster(models.Model):
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=ClusterStatus.choices,
        default=ClusterStatus.AVAILABLE,
    )
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clusters",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "number"]

    def __str__(self):
        return f"Cluster #{self.number} ({self.status})"


class Order(models.Model):
    address = models.CharField(max_length=255)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.NEED,
    )

    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    cluster = models.ForeignKey(
        Cluster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    route_position = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        old_status = None
        old_address = None

        if self.pk:
            old_order = Order.objects.filter(pk=self.pk).only("status", "address").first()
            if old_order:
                old_status = old_order.status
                old_address = old_order.address

        address_changed = self.pk is not None and old_address != self.address
        coordinates_missing = self.latitude is None or self.longitude is None

        should_geocode = self.address and (address_changed or coordinates_missing)

        if should_geocode:
            coordinates = geocode_chelyabinsk_address(self.address)

            if coordinates is not None:
                self.latitude, self.longitude = coordinates
            elif address_changed:
                self.latitude = None
                self.longitude = None

        super().save(*args, **kwargs)

        if old_status is not None and old_status != self.status:
            OrderHistory.objects.create(
                order=self,
                old_status=old_status,
                new_status=self.status,
            )

    def __str__(self):
        return f"Order #{self.id} - {self.address}"


class OrderHistory(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="history",
    )
    old_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    new_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"History for Order #{self.order_id}: {self.old_status} -> {self.new_status}"