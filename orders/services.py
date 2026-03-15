from decimal import Decimal
from math import atan2, cos, radians, sin, sqrt

from django.db import transaction

from .models import Cluster, ClusterStatus, Order, OrderStatus


def haversine_distance_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371

    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius_km * c


def build_cluster_hull_points(orders):
    unique_points = sorted(
        {(float(order.longitude), float(order.latitude)) for order in orders}
    )

    if len(unique_points) < 3:
        return []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in unique_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]

    return [
        {"lat": round(lat, 6), "lng": round(lng, 6)}
        for lng, lat in hull
    ]


def build_order_clusters(
    orders,
    max_cluster_size=10,
    max_distance_km=3.0,
    max_total_weight=Decimal("100"),
):
    prepared_orders = sorted(
        list(orders),
        key=lambda order: (order.latitude, order.longitude, order.id),
    )

    unassigned = prepared_orders[:]
    clusters = []
    cluster_number = 1

    while unassigned:
        seed_order = unassigned.pop(0)
        cluster_orders = [seed_order]

        while unassigned and len(cluster_orders) < max_cluster_size:
            center_lat = sum(order.latitude for order in cluster_orders) / len(cluster_orders)
            center_lon = sum(order.longitude for order in cluster_orders) / len(cluster_orders)
            current_total_weight = sum(
                (order.weight for order in cluster_orders),
                Decimal("0"),
            )

            valid_candidates = []

            for index, candidate in enumerate(unassigned):
                distance_km = haversine_distance_km(
                    candidate.latitude,
                    candidate.longitude,
                    center_lat,
                    center_lon,
                )

                new_total_weight = current_total_weight + candidate.weight

                if distance_km <= max_distance_km and new_total_weight <= max_total_weight:
                    valid_candidates.append((index, distance_km))

            if not valid_candidates:
                break

            nearest_index, _ = min(valid_candidates, key=lambda item: item[1])
            cluster_orders.append(unassigned.pop(nearest_index))

        center_lat = sum(order.latitude for order in cluster_orders) / len(cluster_orders)
        center_lon = sum(order.longitude for order in cluster_orders) / len(cluster_orders)
        total_weight = sum((order.weight for order in cluster_orders), Decimal("0"))

        clusters.append(
            {
                "number": cluster_number,
                "orders": cluster_orders,
                "order_count": len(cluster_orders),
                "center_lat": round(center_lat, 6),
                "center_lon": round(center_lon, 6),
                "total_weight": total_weight,
                "hull_points": build_cluster_hull_points(cluster_orders),
            }
        )
        cluster_number += 1

    return clusters


def build_nearest_neighbor_route_points(office, orders):
    route_points = [
        {
            "lat": office["latitude"],
            "lng": office["longitude"],
            "label": office["name"],
            "kind": "office",
        }
    ]

    unvisited = [
        {
            "order_id": order.id,
            "lat": order.latitude,
            "lng": order.longitude,
            "address": order.address,
        }
        for order in orders
        if order.latitude is not None and order.longitude is not None
    ]

    current_lat = office["latitude"]
    current_lng = office["longitude"]
    stop_number = 1

    while unvisited:
        nearest_index = min(
            range(len(unvisited)),
            key=lambda index: haversine_distance_km(
                current_lat,
                current_lng,
                unvisited[index]["lat"],
                unvisited[index]["lng"],
            ),
        )

        nearest = unvisited.pop(nearest_index)

        route_points.append(
            {
                "lat": nearest["lat"],
                "lng": nearest["lng"],
                "label": nearest["address"],
                "kind": "order",
                "order_id": nearest["order_id"],
                "stop_number": stop_number,
            }
        )

        current_lat = nearest["lat"]
        current_lng = nearest["lng"]
        stop_number += 1

    return route_points


@transaction.atomic
def rebuild_available_clusters(
    max_cluster_size=10,
    max_distance_km=3,
    max_total_weight=Decimal("100"),
):
    Cluster.objects.filter(status=ClusterStatus.AVAILABLE).delete()

    source_orders = list(
        Order.objects.filter(
            status=OrderStatus.NEED,
            courier__isnull=True,
            latitude__isnull=False,
            longitude__isnull=False,
        ).order_by("id")
    )

    clusters_data = build_order_clusters(
        source_orders,
        max_cluster_size=max_cluster_size,
        max_distance_km=max_distance_km,
        max_total_weight=max_total_weight,
    )

    created_clusters = []

    for cluster_data in clusters_data:
        cluster = Cluster.objects.create(
            number=cluster_data["number"],
            status=ClusterStatus.AVAILABLE,
        )

        order_ids = [order.id for order in cluster_data["orders"]]
        Order.objects.filter(id__in=order_ids).update(cluster=cluster)

        created_clusters.append(cluster)

    return created_clusters