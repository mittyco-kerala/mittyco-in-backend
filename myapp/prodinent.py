"""Small, backend-only client for the Prodinent Partner API.

The connection key is intentionally read from Django settings and is never
accepted from a browser request.  Live write calls remain disabled unless the
deployment explicitly enables them.
"""

from urllib.parse import urlsplit
import uuid
from decimal import Decimal, InvalidOperation
import logging

import requests

from django.conf import settings
from django.utils import timezone

from .shipping import lookup_pincode_state


logger = logging.getLogger(__name__)


class ProdinentAPIError(RuntimeError):
    """An unavailable, invalid, or rejected Prodinent API operation."""

    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class ProdinentService:
    """Authenticated calls to the allow-listed Prodinent API host."""

    API_HOST = "api.prodinent.com"

    @classmethod
    def _settings(cls):
        enabled = bool(getattr(settings, "PRODINENT_ENABLED", False))
        base_url = str(
            getattr(
                settings,
                "PRODINENT_BASE_URL",
                "https://api.prodinent.com/api/v1",
            )
            or ""
        ).strip().rstrip("/")
        connection_key = str(
            getattr(settings, "PRODINENT_CONNECTION_KEY", "") or ""
        ).strip()
        try:
            timeout = float(getattr(settings, "PRODINENT_TIMEOUT", 15))
        except (TypeError, ValueError):
            timeout = 15.0

        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname != cls.API_HOST:
            raise ProdinentAPIError("Prodinent API URL is not allowed.")
        if not parsed.path.rstrip("/").endswith("/api/v1"):
            raise ProdinentAPIError("Prodinent API URL is invalid.")
        if not connection_key:
            raise ProdinentAPIError("Prodinent connection key is not configured.")
        if timeout <= 0:
            raise ProdinentAPIError("Prodinent API timeout is invalid.")
        if not enabled:
            raise ProdinentAPIError("Prodinent integration is disabled.")
        return base_url, connection_key, timeout

    @classmethod
    def _request(cls, method, path, *, payload=None, allow_write=False):
        base_url, connection_key, timeout = cls._settings()
        if allow_write and not getattr(settings, "PRODINENT_LIVE_WRITES_ENABLED", False):
            raise ProdinentAPIError("Prodinent live writes are disabled.")

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {connection_key}",
            "X-Request-Id": str(uuid.uuid4()),
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            response = requests.request(
                method,
                f"{base_url}{path}",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as error:
            raise ProdinentAPIError(
                "Prodinent is temporarily unavailable."
            ) from error

        try:
            response_payload = response.json()
        except ValueError as error:
            raise ProdinentAPIError(
                "Prodinent returned an invalid response.",
                status_code=response.status_code,
            ) from error

        if not response.ok:
            raise ProdinentAPIError(
                "Prodinent rejected the request.",
                status_code=response.status_code,
            )
        if not isinstance(response_payload, dict):
            raise ProdinentAPIError(
                "Prodinent returned an invalid response.",
                status_code=response.status_code,
            )
        if response_payload.get("success") is False:
            raise ProdinentAPIError(
                "Prodinent rejected the request.",
                status_code=response.status_code,
            )
        return response_payload

    @classmethod
    def check_connection(cls):
        return cls._request("GET", "/me")

    @classmethod
    def list_warehouses(cls):
        return cls._request("GET", "/warehouses")

    @classmethod
    def create_order(cls, payload):
        if not isinstance(payload, dict):
            raise ProdinentAPIError("Prodinent order payload must be an object.")
        return cls._request("POST", "/orders", payload=payload, allow_write=True)

    @classmethod
    def get_order(cls, external_order_id):
        return cls._request("GET", f"/orders/{cls._order_id(external_order_id)}")

    @classmethod
    def book_order(cls, external_order_id, *, warehouse_id=None):
        payload = {"warehouseId": warehouse_id} if warehouse_id else None
        return cls._request(
            "POST",
            f"/orders/{cls._order_id(external_order_id)}/book",
            payload=payload,
            allow_write=True,
        )

    @classmethod
    def track_order(cls, external_order_id):
        return cls._request(
            "GET",
            f"/orders/{cls._order_id(external_order_id)}/tracking",
        )

    @staticmethod
    def _order_id(value):
        order_id = str(value or "").strip()
        if not order_id or len(order_id) > 80 or any(char in order_id for char in "/?#"):
            raise ProdinentAPIError("Prodinent external order ID is invalid.")
        return order_id


def _order_items(order):
    items = getattr(order, "items", [])
    return list(items.all()) if hasattr(items, "all") else list(items)


def _number(value, *, default=0.0):
    try:
        return float(Decimal(str(value if value is not None else default)))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ProdinentAPIError("Order contains an invalid numeric value.") from error


def _item_identifier(item):
    variant_unit = getattr(item, "variant_unit", None)
    variant = getattr(variant_unit, "variant", None) if variant_unit else None
    sku = str(
        getattr(variant_unit, "sku", None)
        or getattr(variant, "sku", None)
        or ""
    ).strip()
    if sku:
        return {"sku": sku}
    if variant_unit and getattr(variant_unit, "id", None):
        return {"externalProductId": f"mittyco-variant-unit-{variant_unit.id}"}
    product = getattr(item, "product", None)
    product_id = getattr(product, "id", None)
    if product_id:
        return {"externalProductId": f"mittyco-product-{product_id}"}
    raise ProdinentAPIError("Order item does not have a product identifier.")


def _item_weight_grams(item):
    variant_unit = getattr(item, "variant_unit", None)
    variant = getattr(variant_unit, "variant", None) if variant_unit else None
    configured = getattr(settings, "INDIA_POST_DEFAULT_ITEM_WEIGHT_GRAMS", 500)
    raw_weight = (
        getattr(variant_unit, "shipping_weight_grams", None)
        if variant_unit
        else None
    )
    raw_weight = raw_weight or getattr(variant, "shipping_weight_grams", None)
    try:
        weight = int(raw_weight or configured)
    except (TypeError, ValueError) as error:
        raise ProdinentAPIError("Order item weight is invalid.") from error
    return max(weight, 1)


def build_order_payload(order, *, warehouse_id=None):
    """Map a paid local order to the documented Prodinent order contract."""

    order_id = getattr(order, "id", None)
    address = getattr(order, "address", None)
    if not order_id or not address:
        raise ProdinentAPIError("Order must have an ID and delivery address.")

    full_name = str(getattr(address, "full_name", "") or "").strip()
    phone = str(getattr(address, "phone", "") or "").strip()
    full_address = str(getattr(address, "address_line", "") or "").strip()
    pincode = str(getattr(address, "postal_code", "") or "").strip()
    city = str(getattr(address, "city", "") or "").strip()
    country = str(getattr(address, "country", "India") or "India").strip()
    if not all((full_name, phone, full_address, pincode, city)):
        raise ProdinentAPIError("Order delivery address is incomplete.")

    state = str(lookup_pincode_state(pincode) or "").strip()
    if not state:
        raise ProdinentAPIError("Delivery state could not be determined from the pincode.")

    products = []
    total_weight = 0
    for item in _order_items(order):
        quantity = int(getattr(item, "quantity", 0) or 0)
        if quantity < 1:
            raise ProdinentAPIError("Order contains an invalid quantity.")
        product = getattr(item, "product", None)
        product_name = str(getattr(product, "name", "") or "").strip()
        if not product_name:
            raise ProdinentAPIError("Order item does not have a product name.")
        line = _item_identifier(item)
        line.update(
            {
                "qty": quantity,
                "unitPrice": _number(getattr(item, "price", 0)),
                "productName": product_name,
            }
        )
        products.append(line)
        total_weight += quantity * _item_weight_grams(item)

    if not products:
        raise ProdinentAPIError("Order contains no products.")

    user = getattr(order, "user", None)
    email = str(getattr(user, "email", "") or "").strip()
    customer = {"name": full_name, "phone": phone}
    if email:
        customer["email"] = email

    payment_method = str(getattr(order, "payment_method", "") or "").upper()
    payment = {"method": "COD" if payment_method == "COD" else "Pre-paid"}
    selected_warehouse = str(
        warehouse_id
        or getattr(settings, "PRODINENT_WAREHOUSE_ID", "")
        or ""
    ).strip()

    payload = {
        "externalOrderId": f"ORD-{int(order_id):06d}",
        "customer": customer,
        "shippingAddress": {
            "name": full_name,
            "phone": phone,
            "fullAddress": full_address,
            "pincode": pincode,
            "city": city,
            "state": state,
            "country": country or "India",
        },
        "products": products,
        "payment": payment,
        "deliveryCharge": _number(getattr(order, "shipping_charge", 0)),
        "shipment": {"weightGrams": total_weight},
        "remarks": f"Mittyco order ORD-{int(order_id):06d}",
    }
    if selected_warehouse:
        payload["warehouseId"] = selected_warehouse
    return payload


def _provider_order(response):
    provider_order = response.get("order") if isinstance(response, dict) else None
    if not isinstance(provider_order, dict) or not provider_order.get("orderID"):
        raise ProdinentAPIError("Prodinent returned an incomplete order response.")
    return provider_order


def apply_order_response(order, response):
    """Persist only the provider identifiers needed for fulfilment/tracking."""

    provider_order = _provider_order(response)
    order.prodinent_order_id = str(provider_order["orderID"])[:80]
    order.prodinent_status = str(provider_order.get("status") or "")[:40]
    order.prodinent_article_id = str(provider_order.get("articleId") or "")[:80] or None
    tracking_link = str(provider_order.get("trackingLink") or "").strip()
    order.prodinent_tracking_link = tracking_link[:500] or None
    order.prodinent_label_available = bool(provider_order.get("labelAvailable"))
    order.prodinent_last_error = None
    order.prodinent_synced_at = timezone.now()
    order.save(
        update_fields=(
            "prodinent_order_id",
            "prodinent_status",
            "prodinent_article_id",
            "prodinent_tracking_link",
            "prodinent_label_available",
            "prodinent_last_error",
            "prodinent_synced_at",
            "updated_at",
        )
    )
    return provider_order


def _record_sync_error(order_id, error):
    from .models import Order

    message = str(error)[:500] or "Prodinent synchronization failed."
    Order.objects.filter(pk=order_id).update(
        prodinent_status="Error",
        prodinent_last_error=message,
        prodinent_synced_at=timezone.now(),
    )


def sync_order_to_prodinent(order_id):
    """Create a paid local order in Prodinent when live writes are enabled."""

    if not (
        getattr(settings, "PRODINENT_ENABLED", False)
        and getattr(settings, "PRODINENT_LIVE_WRITES_ENABLED", False)
    ):
        return None

    from .models import Order

    order = (
        Order.objects.select_related("user", "address")
        .prefetch_related(
            "items__product",
            "items__variant_unit__variant",
        )
        .get(pk=order_id)
    )
    if order.prodinent_order_id:
        return {"orderID": order.prodinent_order_id, "duplicate": True}

    try:
        response = ProdinentService.create_order(build_order_payload(order))
        apply_order_response(order, response)
        logger.info(
            "Prodinent order created for local order %s with status %s",
            order.id,
            order.prodinent_status,
        )
        return response
    except ProdinentAPIError as error:
        _record_sync_error(order.id, error)
        logger.exception("Prodinent order synchronization failed for local order %s", order.id)
        return None


def book_local_order_in_prodinent(order_id):
    """Book one already-created Prodinent order from a protected admin action."""

    from .models import Order

    order = Order.objects.get(pk=order_id)
    # Prodinent's booking route is addressed by our externalOrderId, not the
    # provider-generated numeric orderID stored on the local order.
    external_order_id = f"ORD-{order.id:06d}"
    try:
        response = ProdinentService.book_order(
            external_order_id,
            warehouse_id=getattr(settings, "PRODINENT_WAREHOUSE_ID", "") or None,
        )
        apply_order_response(order, response)
        return response
    except ProdinentAPIError as error:
        _record_sync_error(order.id, error)
        logger.exception("Prodinent booking failed for local order %s", order.id)
        return None

