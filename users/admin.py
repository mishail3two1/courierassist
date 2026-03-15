from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "id",
        "username",
        "role",
        "telegram_user_id",
        "telegram_username",
        "is_staff",
        "is_superuser",
    )
    list_filter = (
        "role",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "telegram_username",
        "telegram_user_id",
    )
    ordering = ("id",)

    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "CourierAssist",
            {
                "fields": (
                    "role",
                    "telegram_user_id",
                    "telegram_username",
                )
            },
        ),
    )

    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "CourierAssist",
            {
                "fields": (
                    "role",
                    "telegram_user_id",
                    "telegram_username",
                )
            },
        ),
    )