from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    COURIER = "courier", "Courier"
    ADMIN = "admin", "Admin"


class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.COURIER,
    )
    telegram_user_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
    )
    telegram_username = models.CharField(
        max_length=255,
        blank=True,
    )

    def __str__(self):
        return self.username