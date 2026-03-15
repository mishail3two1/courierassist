from decimal import Decimal
from random import sample, uniform

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Cluster, ClusterStatus, Order, OrderStatus
from .services import (
    build_cluster_hull_points,
    build_nearest_neighbor_route_points,
    haversine_distance_km,
    rebuild_available_clusters,
)

User = get_user_model()

MAX_CLUSTER_SIZE = 10
MAX_DISTANCE_KM = 3.0
MAX_TOTAL_WEIGHT = Decimal("100")

SAMPLE_CHELYABINSK_ADDRESSES = [
    {"address": "проспект Ленина, 35", "latitude": 55.1609, "longitude": 61.4021},
    {"address": "проспект Ленина, 64", "latitude": 55.1602, "longitude": 61.4210},
    {"address": "улица Кирова, 86", "latitude": 55.1648, "longitude": 61.4004},
    {"address": "улица Труда, 95", "latitude": 55.1716, "longitude": 61.3958},
    {"address": "улица Энтузиастов, 12", "latitude": 55.1580, "longitude": 61.3815},
    {"address": "улица Братьев Кашириных, 120", "latitude": 55.1795, "longitude": 61.3215},
    {"address": "улица Чичерина, 35А", "latitude": 55.1760, "longitude": 61.3034},
    {"address": "улица Молодогвардейцев, 60", "latitude": 55.1920, "longitude": 61.3155},
    {"address": "улица 40-летия Победы, 33", "latitude": 55.1955, "longitude": 61.3062},
    {"address": "Комсомольский проспект, 90", "latitude": 55.2085, "longitude": 61.3310},
    {"address": "улица Салавата Юлаева, 17", "latitude": 55.1884, "longitude": 61.2896},
    {"address": "улица Академика Королёва, 24", "latitude": 55.1840, "longitude": 61.2875},
    {"address": "улица Воровского, 17", "latitude": 55.1487, "longitude": 61.3812},
    {"address": "улица Российская, 220", "latitude": 55.1555, "longitude": 61.4350},
    {"address": "улица Гагарина, 15", "latitude": 55.1298, "longitude": 61.4520},
    {"address": "улица Дзержинского, 93", "latitude": 55.1135, "longitude": 61.4300},
    {"address": "Копейское шоссе, 5", "latitude": 55.1252, "longitude": 61.4680},
    {"address": "улица Каслинская, 97", "latitude": 55.1880, "longitude": 61.3990},
    {"address": "проспект Победы, 160", "latitude": 55.2010, "longitude": 61.3905},
    {"address": "улица Свободы, 108", "latitude": 55.1530, "longitude": 61.4185},
]


def get_linked_telegram_user_from_session(request):
    telegram_debug_user = request.session.get("telegram_debug_user")

    if not telegram_debug_user:
        return None, None

    telegram_id = telegram_debug_user.get("id")
    if not telegram_id:
        return telegram_debug_user, None

    linked_user = User.objects.filter(telegram_user_id=telegram_id).first()
    return telegram_debug_user, linked_user


def order_list(request):
    orders = Order.objects.select_related("courier", "cluster").order_by("-created_at")

    context = {
        "orders": orders,
    }
    return render(request, "orders/order_list.html", context)


@login_required
def my_orders(request):
    status = request.GET.get("status", "").strip()

    orders = (
        Order.objects.select_related("courier", "cluster")
        .filter(courier=request.user)
        .order_by("-created_at")
    )

    allowed_statuses = {
        OrderStatus.NEED,
        OrderStatus.IN_PROGRESS,
        OrderStatus.DELIVERED,
    }

    if status in allowed_statuses:
        orders = orders.filter(status=status)
    else:
        status = ""

    context = {
        "orders": orders,
        "current_status": status,
    }
    return render(request, "orders/my_orders.html", context)


@login_required
def generate_test_orders(request):
    created_count = request.GET.get("created")
    max_available = len(SAMPLE_CHELYABINSK_ADDRESSES)

    if request.method == "POST":
        try:
            count = int(request.POST.get("count", "20"))
        except ValueError:
            count = 20

        count = max(1, min(count, max_available))

        selected_addresses = sample(SAMPLE_CHELYABINSK_ADDRESSES, count)

        for item in selected_addresses:
            Order.objects.create(
                address=item["address"],
                latitude=item["latitude"],
                longitude=item["longitude"],
                weight=Decimal(f"{uniform(0.50, 15.00):.2f}"),
                price=Decimal(f"{uniform(150.00, 900.00):.2f}"),
                status=OrderStatus.NEED,
                courier=None,
                cluster=None,
                route_position=None,
            )

        return redirect(f"{reverse('generate_test_orders')}?created={count}")

    context = {
        "created_count": created_count,
        "max_available": max_available,
    }
    return render(request, "orders/generate_test_orders.html", context)


@login_required
@require_POST
def take_order(request, order_id):
    return redirect("order_map")


@login_required
@require_POST
def complete_order(request, order_id):
    return redirect("order_map")


def order_map(request):
    if request.method == "POST" and request.POST.get("action") == "save_telegram_user_debug":
        telegram_user = {
            "id": request.POST.get("telegram_id", "").strip(),
            "username": request.POST.get("telegram_username", "").strip(),
            "first_name": request.POST.get("telegram_first_name", "").strip(),
            "last_name": request.POST.get("telegram_last_name", "").strip(),
            "language_code": request.POST.get("telegram_language_code", "").strip(),
        }

        request.session["telegram_debug_user"] = telegram_user
        request.session.modified = True

        return JsonResponse(
            {
                "ok": True,
                "telegram_user": telegram_user,
            }
        )

    if request.method == "POST" and request.POST.get("action") == "link_telegram_account":
        telegram_user = request.session.get("telegram_debug_user")

        if not request.user.is_authenticated:
            request.session["telegram_link_result"] = {
                "ok": False,
                "text": "Сначала войдите в Django-аккаунт, а потом привязывайте Telegram.",
            }
            return redirect("order_map")

        if not telegram_user or not telegram_user.get("id"):
            request.session["telegram_link_result"] = {
                "ok": False,
                "text": "Telegram-пользователь ещё не получен на этой странице.",
            }
            return redirect("order_map")

        existing_user = User.objects.filter(
            telegram_user_id=telegram_user["id"]
        ).exclude(pk=request.user.pk).first()

        if existing_user:
            request.session["telegram_link_result"] = {
                "ok": False,
                "text": "Этот Telegram уже привязан к другому пользователю.",
            }
            return redirect("order_map")

        request.user.telegram_user_id = int(telegram_user["id"])
        request.user.telegram_username = telegram_user.get("username", "")
        request.user.save(update_fields=["telegram_user_id", "telegram_username"])

        request.session["telegram_link_result"] = {
            "ok": True,
            "text": "Telegram успешно привязан к вашему аккаунту.",
        }
        return redirect("order_map")

    office = {
        "name": "Офис CourierAssist",
        "latitude": 55.1603,
        "longitude": 61.4026,
    }

    cluster_points = []
    cluster_areas = []
    cluster_count = 0
    active_cluster_mode = False
    active_cluster_number = None
    route_points = []

    active_cluster = None
    active_cluster_orders = []

    telegram_debug_user, linked_telegram_user = get_linked_telegram_user_from_session(request)
    telegram_link_result = request.session.pop("telegram_link_result", None)

    if request.user.is_authenticated:
        candidate_clusters = (
            Cluster.objects.filter(
                status=ClusterStatus.TAKEN,
                courier=request.user,
            )
            .prefetch_related("orders")
            .order_by("-created_at", "-id")
        )

        for candidate_cluster in candidate_clusters:
            candidate_orders = list(
                candidate_cluster.orders.filter(
                    latitude__isnull=False,
                    longitude__isnull=False,
                ).order_by("route_position", "id")
            )

            if candidate_orders:
                active_cluster = candidate_cluster
                active_cluster_orders = candidate_orders
                break

    if not active_cluster:
        rebuild_available_clusters(
            max_cluster_size=MAX_CLUSTER_SIZE,
            max_distance_km=MAX_DISTANCE_KM,
            max_total_weight=MAX_TOTAL_WEIGHT,
        )

    if active_cluster:
        orders = active_cluster_orders

        active_cluster_mode = True
        active_cluster_number = active_cluster.number
        cluster_count = 1
        area_color = "#808080"

        center_lat = round(sum(order.latitude for order in orders) / len(orders), 6)
        center_lon = round(sum(order.longitude for order in orders) / len(orders), 6)
        total_weight = sum((order.weight for order in orders), Decimal("0"))
        hull_points = build_cluster_hull_points(orders)

        route_points = [
            {
                "lat": office["latitude"],
                "lng": office["longitude"],
                "label": office["name"],
                "kind": "office",
            }
        ]

        ordered_route_orders = [
            order for order in orders
            if order.route_position is not None and order.status != OrderStatus.DELIVERED
        ]
        ordered_route_orders.sort(key=lambda order: order.route_position)

        for order in ordered_route_orders:
            route_points.append(
                {
                    "lat": order.latitude,
                    "lng": order.longitude,
                    "label": order.address,
                    "kind": "order",
                    "order_id": order.id,
                    "stop_number": order.route_position,
                }
            )

        max_radius_m = 0
        delivered_count = 0

        for order in orders:
            distance_km = haversine_distance_km(
                center_lat,
                center_lon,
                order.latitude,
                order.longitude,
            )
            max_radius_m = max(max_radius_m, distance_km * 1000)

            is_delivered = order.status == OrderStatus.DELIVERED
            point_color = "#2e7d32" if is_delivered else "#808080"

            if is_delivered:
                delivered_count += 1

            cluster_points.append(
                {
                    "cluster_id": active_cluster.id,
                    "cluster_number": active_cluster.number,
                    "color": point_color,
                    "id": order.id,
                    "address": order.address,
                    "status": order.get_status_display(),
                    "weight": str(order.weight),
                    "latitude": order.latitude,
                    "longitude": order.longitude,
                    "is_active": True,
                    "is_delivered": is_delivered,
                    "complete_url": f"/orders/{order.id}/complete-from-map/" if not is_delivered else "",
                    "route_position": order.route_position,
                }
            )

        if len(hull_points) >= 3:
            cluster_areas.append(
                {
                    "cluster_id": active_cluster.id,
                    "cluster_number": active_cluster.number,
                    "color": area_color,
                    "type": "polygon",
                    "points": hull_points,
                    "order_count": len(orders),
                    "delivered_count": delivered_count,
                    "total_weight": str(total_weight),
                    "is_active": True,
                }
            )
        else:
            cluster_areas.append(
                {
                    "cluster_id": active_cluster.id,
                    "cluster_number": active_cluster.number,
                    "color": area_color,
                    "type": "circle",
                    "center_lat": center_lat,
                    "center_lon": center_lon,
                    "radius_m": max(150, round(max_radius_m + 100)),
                    "order_count": len(orders),
                    "delivered_count": delivered_count,
                    "total_weight": str(total_weight),
                    "is_active": True,
                }
            )

    else:
        saved_clusters = (
            Cluster.objects.filter(status=ClusterStatus.AVAILABLE)
            .prefetch_related("orders")
            .order_by("number")
        )

        palette = [
            "#e53935",
            "#1e88e5",
            "#43a047",
            "#8e24aa",
            "#fb8c00",
            "#00897b",
            "#6d4c41",
            "#3949ab",
            "#d81b60",
            "#7cb342",
        ]

        cluster_count = len(saved_clusters)

        for cluster in saved_clusters:
            orders = list(
                cluster.orders.filter(
                    latitude__isnull=False,
                    longitude__isnull=False,
                ).order_by("id")
            )
            if not orders:
                continue

            color = palette[(cluster.number - 1) % len(palette)]

            center_lat = round(sum(order.latitude for order in orders) / len(orders), 6)
            center_lon = round(sum(order.longitude for order in orders) / len(orders), 6)
            total_weight = sum((order.weight for order in orders), Decimal("0"))
            hull_points = build_cluster_hull_points(orders)

            max_radius_m = 0
            for order in orders:
                distance_km = haversine_distance_km(
                    center_lat,
                    center_lon,
                    order.latitude,
                    order.longitude,
                )
                max_radius_m = max(max_radius_m, distance_km * 1000)

                cluster_points.append(
                    {
                        "cluster_id": cluster.id,
                        "cluster_number": cluster.number,
                        "color": color,
                        "id": order.id,
                        "address": order.address,
                        "status": order.get_status_display(),
                        "weight": str(order.weight),
                        "latitude": order.latitude,
                        "longitude": order.longitude,
                        "is_active": False,
                        "is_delivered": False,
                        "complete_url": "",
                        "route_position": None,
                    }
                )

            area_base = {
                "cluster_id": cluster.id,
                "cluster_number": cluster.number,
                "color": color,
                "order_count": len(orders),
                "delivered_count": 0,
                "total_weight": str(total_weight),
                "take_url": f"/orders/clusters/{cluster.id}/take/",
                "is_active": False,
            }

            if len(hull_points) >= 3:
                cluster_areas.append(
                    {
                        **area_base,
                        "type": "polygon",
                        "points": hull_points,
                    }
                )
            else:
                cluster_areas.append(
                    {
                        **area_base,
                        "type": "circle",
                        "center_lat": center_lat,
                        "center_lon": center_lon,
                        "radius_m": max(150, round(max_radius_m + 100)),
                    }
                )

    context = {
        "cluster_points": cluster_points,
        "cluster_areas": cluster_areas,
        "office": office,
        "cluster_count": cluster_count,
        "max_cluster_size": MAX_CLUSTER_SIZE,
        "max_distance_km": MAX_DISTANCE_KM,
        "max_total_weight": MAX_TOTAL_WEIGHT,
        "active_cluster_mode": active_cluster_mode,
        "active_cluster_number": active_cluster_number,
        "route_points": route_points,
        "telegram_debug_user": telegram_debug_user,
        "linked_telegram_user": linked_telegram_user,
        "telegram_link_result": telegram_link_result,
    }
    return render(request, "orders/order_map.html", context)


def order_clusters(request):
    saved_clusters = (
        Cluster.objects.filter(status=ClusterStatus.AVAILABLE)
        .prefetch_related("orders")
        .order_by("number")
    )

    cluster_cards = []
    total_clustered_orders = 0

    for cluster in saved_clusters:
        orders = list(cluster.orders.all().order_by("id"))
        if not orders:
            continue

        total_weight = sum((order.weight for order in orders), Decimal("0"))
        center_lat = round(sum(order.latitude for order in orders) / len(orders), 6)
        center_lon = round(sum(order.longitude for order in orders) / len(orders), 6)

        total_clustered_orders += len(orders)

        cluster_cards.append(
            {
                "id": cluster.id,
                "number": cluster.number,
                "orders": orders,
                "order_count": len(orders),
                "center_lat": center_lat,
                "center_lon": center_lon,
                "total_weight": total_weight,
            }
        )

    orders_without_coordinates = Order.objects.filter(
        status=OrderStatus.NEED,
        courier__isnull=True,
    ).filter(
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    ).count()

    context = {
        "clusters": cluster_cards,
        "total_clustered_orders": total_clustered_orders,
        "orders_without_coordinates": orders_without_coordinates,
        "max_cluster_size": MAX_CLUSTER_SIZE,
        "max_distance_km": MAX_DISTANCE_KM,
        "max_total_weight": MAX_TOTAL_WEIGHT,
    }
    return render(request, "orders/cluster_list.html", context)


@require_POST
def rebuild_clusters(request):
    rebuild_available_clusters(
        max_cluster_size=MAX_CLUSTER_SIZE,
        max_distance_km=MAX_DISTANCE_KM,
        max_total_weight=MAX_TOTAL_WEIGHT,
    )
    return redirect("order_clusters")


@login_required
def take_cluster_confirm(request, cluster_id):
    cluster = get_object_or_404(
        Cluster.objects.prefetch_related("orders"),
        pk=cluster_id,
        status=ClusterStatus.AVAILABLE,
    )

    orders = list(cluster.orders.all().order_by("id"))
    total_weight = sum((order.weight for order in orders), Decimal("0"))

    context = {
        "cluster": cluster,
        "orders": orders,
        "total_weight": total_weight,
    }
    return render(request, "orders/cluster_take_confirm.html", context)


@login_required
@require_POST
@transaction.atomic
def take_cluster(request, cluster_id):
    cluster = get_object_or_404(Cluster, pk=cluster_id)

    if cluster.status != ClusterStatus.AVAILABLE:
        return redirect("order_map")

    cluster.status = ClusterStatus.TAKEN
    cluster.courier = request.user
    cluster.save()

    cluster_orders = list(
        cluster.orders.filter(
            status=OrderStatus.NEED,
            courier__isnull=True,
            latitude__isnull=False,
            longitude__isnull=False,
        ).order_by("id")
    )

    route_points = build_nearest_neighbor_route_points(
        {
            "name": "Офис CourierAssist",
            "latitude": 55.1603,
            "longitude": 61.4026,
        },
        cluster_orders,
    )

    order_position_map = {}
    for point in route_points:
        if point.get("kind") == "order":
            order_position_map[point["order_id"]] = point["stop_number"]

    for order in cluster_orders:
        order.courier = request.user
        order.status = OrderStatus.IN_PROGRESS
        order.delivered_at = None
        order.route_position = order_position_map.get(order.id)
        order.save()

    return redirect("order_map")


@login_required
@require_POST
@transaction.atomic
def complete_order_from_map(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("cluster"),
        pk=order_id,
        courier=request.user,
        cluster__courier=request.user,
        cluster__status=ClusterStatus.TAKEN,
    )

    is_ajax_request = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if order.status == OrderStatus.IN_PROGRESS:
        order.status = OrderStatus.DELIVERED
        order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_at"])

    cluster = order.cluster

    remaining_orders = cluster.orders.exclude(status=OrderStatus.DELIVERED)

    if not remaining_orders.exists():
        cluster.status = ClusterStatus.COMPLETED
        cluster.save(update_fields=["status"])

        if is_ajax_request:
            return JsonResponse(
                {
                    "ok": True,
                    "order_id": order.id,
                    "status": order.get_status_display(),
                    "cluster_completed": True,
                    "redirect_url": reverse("cluster_completed", kwargs={"cluster_id": cluster.id}),
                }
            )

        return redirect("cluster_completed", cluster_id=cluster.id)

    if is_ajax_request:
        delivered_count = cluster.orders.filter(status=OrderStatus.DELIVERED).count()
        return JsonResponse(
            {
                "ok": True,
                "order_id": order.id,
                "status": order.get_status_display(),
                "cluster_completed": False,
                "delivered_count": delivered_count,
            }
        )

    return redirect("order_map")


@login_required
def cluster_completed(request, cluster_id):
    cluster = get_object_or_404(
        Cluster.objects.prefetch_related("orders"),
        pk=cluster_id,
        courier=request.user,
        status=ClusterStatus.COMPLETED,
    )

    orders = list(cluster.orders.all().order_by("id"))
    total_earnings = sum((order.price for order in orders), Decimal("0"))
    total_weight = sum((order.weight for order in orders), Decimal("0"))
    delivered_count = len(orders)

    context = {
        "cluster": cluster,
        "delivered_count": delivered_count,
        "total_earnings": total_earnings,
        "total_weight": total_weight,
    }
    return render(request, "orders/cluster_completed.html", context)


def cluster_map(request):
    return redirect("order_map")