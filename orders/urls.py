from django.urls import path

from .views import (
    cluster_completed,
    cluster_map,
    complete_order,
    complete_order_from_map,
    generate_test_orders,
    my_orders,
    order_clusters,
    order_list,
    order_map,
    rebuild_clusters,
    take_cluster,
    take_cluster_confirm,
    take_order,
)

urlpatterns = [
    path("", order_list, name="order_list"),
    path("my/", my_orders, name="my_orders"),
    path("map/", order_map, name="order_map"),
    path("generate-test-orders/", generate_test_orders, name="generate_test_orders"),
    path("clusters/", order_clusters, name="order_clusters"),
    path("clusters/rebuild/", rebuild_clusters, name="rebuild_clusters"),
    path("clusters/map/", cluster_map, name="cluster_map"),
    path("clusters/<int:cluster_id>/take/", take_cluster_confirm, name="take_cluster_confirm"),
    path("clusters/<int:cluster_id>/take/confirm/", take_cluster, name="take_cluster"),
    path("clusters/<int:cluster_id>/completed/", cluster_completed, name="cluster_completed"),
    path("<int:order_id>/complete-from-map/", complete_order_from_map, name="complete_order_from_map"),
    path("take/<int:order_id>/", take_order, name="take_order"),
    path("complete/<int:order_id>/", complete_order, name="complete_order"),
]