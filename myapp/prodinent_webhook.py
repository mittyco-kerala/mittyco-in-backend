"""Authenticated Prodinent tracking webhook receiver."""

import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Order
from .prodinent import (
    apply_tracking_response,
    local_order_status_for_prodinent,
)


SIGNATURE_HEADERS = (
    "HTTP_X_WEBHOOK_SIGNATURE",
    "HTTP_X_PRODINENT_SIGNATURE",
    "HTTP_X_POSTBRIDGE_SIGNATURE",
)


def _signature_is_valid(request, raw_body):
    secret = str(getattr(settings, "PRODINENT_WEBHOOK_SECRET", "") or "").strip()
    if not secret:
        return False
    received = next(
        (str(request.META.get(header) or "").strip() for header in SIGNATURE_HEADERS if request.META.get(header)),
        "",
    )
    if received.startswith("sha256="):
        received = received[7:]
    if received:
        if len(received) != 64:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received.lower(), expected.lower())

    # Prodinent's webhook form currently provides only a URL, not a signing
    # secret/header. A long random query token keeps this endpoint private
    # without accepting unsigned public requests.
    token = str(request.GET.get("token") or "").strip()
    return bool(token) and hmac.compare_digest(token, secret)


def _records(payload):
    records = []
    if isinstance(payload, dict):
        records.append(payload)
        for key in ("order", "data", "event"):
            value = payload.get(key)
            if isinstance(value, dict):
                records.append(value)
                nested = value.get("order")
                if isinstance(nested, dict):
                    records.append(nested)
    return records


def _value(records, *keys):
    for record in records:
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return ""


def _find_order(external_order_id):
    order = Order.objects.filter(prodinent_order_id=external_order_id).first()
    if order:
        return order
    if external_order_id.upper().startswith("ORD-"):
        try:
            return Order.objects.filter(pk=int(external_order_id[4:])).first()
        except ValueError:
            return None
    return None


@csrf_exempt
def prodinent_webhook(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed."}, status=405)
    raw_body = request.body
    if len(raw_body) > 256 * 1024:
        return JsonResponse({"message": "Webhook payload is too large."}, status=413)
    if not _signature_is_valid(request, raw_body):
        return JsonResponse({"message": "Invalid webhook signature."}, status=401)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"message": "Invalid webhook payload."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"message": "Invalid webhook payload."}, status=400)

    records = _records(payload)
    external_order_id = _value(records, "externalOrderId", "external_order_id", "orderId")
    if not external_order_id:
        return JsonResponse({"message": "Webhook order ID is required."}, status=400)
    order = _find_order(external_order_id)
    if not order:
        # A valid event for another connection should not be retried forever.
        return JsonResponse({"received": True, "matched": False})

    with transaction.atomic():
        apply_tracking_response(order, payload)
        order.refresh_from_db()
        provider_status = _value(records, "status", "trackingStatus", "state")
        local_status = local_order_status_for_prodinent(provider_status, order.status)
        if local_status != order.status:
            order.status = local_status
            order.save(update_fields=("status", "updated_at"))
    return JsonResponse({"received": True, "matched": True})
