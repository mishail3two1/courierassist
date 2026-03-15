from django.contrib import admin

from .models import Cluster, Order, OrderHistory


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ("id", "number", "status", "courier", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("number", "courier__username")
    ordering = ("-created_at", "number")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "address", "status", "cluster", "courier", "created_at")
    list_filter = ("status", "created_at", "cluster")
    search_fields = ("address",)
    ordering = ("-created_at",)


@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "old_status", "new_status", "changed_at")
    list_filter = ("old_status", "new_status", "changed_at")
    search_fields = ("order__address",)
    ordering = ("-changed_at",)