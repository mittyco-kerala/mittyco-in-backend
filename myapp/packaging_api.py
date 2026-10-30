from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Order, PackagingSlip, PackagingSlipItem
from .permissions import IsSuperAdmin
from .serializers import PackagingSlipSerializer


class PackagingSlipCreateSerializer(serializers.Serializer):
    order_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=100,
    )

    def validate_order_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("order_ids must contain unique order IDs.")
        return value


def _packaging_slip_queryset():
    return PackagingSlip.objects.prefetch_related(
        "orders__user",
        "orders__address",
        "items__order_item__order",
        "items__order_item__product__variants__images",
        "items__order_item__color",
        "items__order_item__unit__unit_type",
        "items__order_item__variant_unit__unit__unit_type",
        "items__order_item__variant_unit__variant",
    )


def _order_set_key(order_ids):
    return ",".join(str(order_id) for order_id in sorted(order_ids))


def _existing_slip(order_ids):
    return (
        _packaging_slip_queryset()
        .filter(order_set_key=_order_set_key(order_ids))
        .order_by("-id")
        .first()
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSuperAdmin])
def create_packaging_slip(request):
    """Create or replay one fulfilment slip for the selected order set."""

    input_serializer = PackagingSlipCreateSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    order_ids = input_serializer.validated_data["order_ids"]

    with transaction.atomic():
        orders = list(
            Order.objects.select_for_update()
            .select_related("user", "address")
            .prefetch_related(
                "items__product__variants__images",
                "items__color",
                "items__unit__unit_type",
                "items__variant_unit__unit__unit_type",
                "items__variant_unit__variant",
            )
            .filter(id__in=order_ids)
        )
        if len(orders) != len(order_ids):
            found_ids = {order.id for order in orders}
            missing_ids = [order_id for order_id in order_ids if order_id not in found_ids]
            return Response(
                {"detail": f"Order(s) not found: {', '.join(map(str, missing_ids))}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = _existing_slip(order_ids)
        if existing:
            return Response(PackagingSlipSerializer(existing).data)

        orders_by_id = {order.id: order for order in orders}
        ordered_orders = [orders_by_id[order_id] for order_id in order_ids]
        slip = PackagingSlip.objects.create(
            created_by=request.user,
            order_set_key=_order_set_key(order_ids),
        )
        slip.orders.set(ordered_orders)

        items = [
            PackagingSlipItem(
                slip=slip,
                order_item=order_item,
                barcode=f"{slip.slip_number}-ITEM-{order_item.id:06d}",
            )
            for order in ordered_orders
            for order_item in order.items.all()
        ]
        PackagingSlipItem.objects.bulk_create(items)

        slip = _packaging_slip_queryset().get(pk=slip.pk)
        return Response(
            PackagingSlipSerializer(slip).data,
            status=status.HTTP_201_CREATED,
        )
