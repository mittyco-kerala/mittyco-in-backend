from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Address


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def india_post_shipping_quote(request):
    """Return the current India Post charge for the user's cart/address."""

    address_id = request.query_params.get("address")
    if not address_id:
        return Response(
            {"message": "A delivery address is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    address = Address.objects.filter(id=address_id, user=request.user).first()
    if not address:
        return Response(
            {"message": "Address not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Import lazily to keep the payment module out of app import time.  Both
    # this quote and payment creation therefore use the same cart snapshot.
    from payment.cashfree_views import _snapshot_from_cart

    try:
        snapshot = _snapshot_from_cart(request.user, address=address)
    except ValueError as error:
        message = str(error)
        response_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if "not configured" in message.lower() or "unavailable" in message.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        return Response({"message": message}, status=response_status)

    quote = snapshot.get("shipping_quote") or {}
    return Response(
        {
            "service": quote.get("service", "India Post Parcel (Retail)"),
            "shipping": snapshot["shipping_charge"],
            "subtotal": snapshot["discounted_subtotal"],
            "total": snapshot["total"],
            "weight_grams": quote.get("weight_grams", 0),
            "origin_pincode": quote.get("origin_pincode", ""),
            "destination_pincode": quote.get("destination_pincode", ""),
            "shipping_class": quote.get("shipping_class", "OTHER_STATE"),
            "free_delivery": quote.get("free_delivery", False),
            "distance_km": quote.get("distance_km"),
            "free_delivery_radius_km": quote.get("free_delivery_radius_km", "5.00"),
            "estimated_delivery_time": quote.get("estimated_delivery_time", ""),
            "rate_version": quote.get("rate_version", ""),
            "currency": "INR",
        },
        status=status.HTTP_200_OK,
    )
