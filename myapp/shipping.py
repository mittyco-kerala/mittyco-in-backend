"""India Post parcel pricing and cart-weight helpers.

The published India Post retail parcel tariff is kept in one small, explicit
table so checkout and payment use the same calculation.  Pincode state lookup
is deliberately optional because the official bulk pincode endpoint requires
the caller's public IP to be whitelisted.
"""

import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from functools import lru_cache
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)

RATE_VERSION = "2026-08-01"
MAX_PARCEL_WEIGHT_GRAMS = 35_000
DEFAULT_ITEM_WEIGHT_GRAMS = 500

# India Post Parcel Retail rates effective 01.08.2026.  Values are base
# retail rates in INR; GST is not silently added because the applicable tax
# treatment must be configured for the merchant's registration.
_RETAIL_RATES = {
    500: {"LOCAL": 28, "WITHIN_STATE": 65, "ZONE_METRO": 70, "OTHER_STATE": 72},
    1000: {"LOCAL": 48, "WITHIN_STATE": 91, "ZONE_METRO": 106, "OTHER_STATE": 114},
    1500: {"LOCAL": 60, "WITHIN_STATE": 117, "ZONE_METRO": 142, "OTHER_STATE": 171},
    2000: {"LOCAL": 87, "WITHIN_STATE": 160, "ZONE_METRO": 198, "OTHER_STATE": 239},
    3000: {"LOCAL": 116, "WITHIN_STATE": 219, "ZONE_METRO": 277, "OTHER_STATE": 337},
    4000: {"LOCAL": 145, "WITHIN_STATE": 268, "ZONE_METRO": 344, "OTHER_STATE": 420},
    5000: {"LOCAL": 174, "WITHIN_STATE": 324, "ZONE_METRO": 420, "OTHER_STATE": 515},
}
_EXTRA_KG_RATES = {"LOCAL": 30, "WITHIN_STATE": 50, "ZONE_METRO": 70, "OTHER_STATE": 90}

_PINCODE_RE = re.compile(r"^\d{6}$")
_WEIGHT_RE = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>kg|kgs|kilogram|kilograms|g|gm|gms|gram|grams)\b",
    re.IGNORECASE,
)


class IndiaPostShippingError(ValueError):
    """Raised when a parcel quote cannot be calculated safely."""


def _valid_pincode(value):
    pincode = str(value or "").strip()
    if not _PINCODE_RE.fullmatch(pincode):
        raise IndiaPostShippingError("A valid six-digit delivery pincode is required.")
    return pincode


def parse_weight_grams(value):
    """Parse only unambiguous gram/kilogram unit labels."""

    match = _WEIGHT_RE.match(str(value or ""))
    if not match:
        return None
    try:
        amount = Decimal(match.group("value"))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    multiplier = Decimal("1000") if match.group("unit").lower().startswith("k") else Decimal("1")
    return int((amount * multiplier).to_integral_value(rounding=ROUND_CEILING))


def _configured_default_weight():
    raw_value = getattr(settings, "INDIA_POST_DEFAULT_ITEM_WEIGHT_GRAMS", DEFAULT_ITEM_WEIGHT_GRAMS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_ITEM_WEIGHT_GRAMS
    return max(value, 1)


def item_shipping_weight_grams(item):
    """Return one cart line's unit weight in grams.

    Explicit admin-entered weights win.  Existing catalogue units such as
    ``250 g`` and ``1 KG`` are supported automatically.  Volume labels such
    as ``1 litre`` intentionally use the configured fallback because volume
    cannot be safely converted to mass for every product.
    """

    variant = getattr(item, "variant", None)
    variant_unit = getattr(item, "variant_unit", None)
    explicit = getattr(variant_unit, "shipping_weight_grams", None) if variant_unit else None
    if explicit is None:
        explicit = getattr(variant, "shipping_weight_grams", None)
    if explicit is not None:
        return max(int(explicit), 1)

    if variant_unit and getattr(variant_unit, "unit", None):
        parsed = parse_weight_grams(getattr(variant_unit.unit, "name", ""))
        if parsed:
            return parsed

    return _configured_default_weight()


def calculate_cart_weight_grams(cart_items):
    total = 0
    for item in cart_items:
        try:
            quantity = int(getattr(item, "quantity", 0) or 0)
        except (TypeError, ValueError):
            quantity = 0
        total += max(quantity, 0) * item_shipping_weight_grams(item)
    return total


def _shipping_class(origin_pincode, destination_pincode, origin_state="", destination_state=""):
    if origin_pincode == destination_pincode:
        return "LOCAL"
    origin = " ".join(str(origin_state or "").split()).casefold()
    destination = " ".join(str(destination_state or "").split()).casefold()
    if origin and destination and origin == destination:
        return "WITHIN_STATE"
    return "OTHER_STATE"


def _base_rate(weight_grams, shipping_class):
    for upper_bound, rates in _RETAIL_RATES.items():
        if weight_grams <= upper_bound:
            return rates[shipping_class]
    extra_kilos = (weight_grams - 5000 + 999) // 1000
    return _RETAIL_RATES[5000][shipping_class] + extra_kilos * _EXTRA_KG_RATES[shipping_class]


def calculate_india_post_charge(
    *,
    weight_grams,
    origin_pincode,
    destination_pincode,
    origin_state="",
    destination_state="",
    gst_rate=Decimal("0"),
):
    try:
        weight = int(weight_grams)
    except (TypeError, ValueError):
        raise IndiaPostShippingError("Parcel weight must be a positive number of grams.")
    if weight < 1 or weight > MAX_PARCEL_WEIGHT_GRAMS:
        raise IndiaPostShippingError("Parcel weight must be between 1 g and 35 kg.")

    origin = _valid_pincode(origin_pincode)
    destination = _valid_pincode(destination_pincode)
    shipping_class = _shipping_class(origin, destination, origin_state, destination_state)
    base_amount = Decimal(str(_base_rate(weight, shipping_class)))
    try:
        tax_rate = Decimal(str(gst_rate or 0))
    except InvalidOperation:
        raise IndiaPostShippingError("India Post GST rate is invalid.")
    if tax_rate < 0 or tax_rate > 100:
        raise IndiaPostShippingError("India Post GST rate must be between 0 and 100.")
    amount = (base_amount * (Decimal("1") + tax_rate / Decimal("100"))).quantize(Decimal("0.01"))

    return {
        "amount": str(amount),
        "base_amount": str(base_amount.quantize(Decimal("0.01"))),
        "weight_grams": weight,
        "shipping_class": shipping_class,
        "rate_version": RATE_VERSION,
        "service": "India Post Parcel (Retail)",
        "gst_rate": str(tax_rate),
    }


@lru_cache(maxsize=512)
def lookup_pincode_state(pincode):
    """Best-effort state lookup through the official India Post endpoint.

    The endpoint rejects requests from IPs that are not whitelisted.  In that
    case an empty state is returned and the calculator safely uses the
    ``OTHER_STATE`` tariff instead of failing a customer's checkout.
    """

    pincode = _valid_pincode(pincode)
    endpoint = str(
        getattr(
            settings,
            "INDIA_POST_PINCODE_API_URL",
            "https://api.cept.gov.in/CommonFacilityMaster/api/values/Pincode",
        )
        or ""
    ).strip()
    if not endpoint:
        return ""
    request = Request(
        endpoint,
        data=json.dumps([{"Input_Pincode": pincode}]).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError) as error:
        logger.warning("India Post pincode lookup unavailable: %s", error)
        if getattr(settings, "INDIA_POST_PINCODE_API_REQUIRED", False):
            raise IndiaPostShippingError(
                "India Post pincode lookup is unavailable. Whitelist the server IP or try again."
            )
        return ""

    rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        state = row.get("StateName") or row.get("State") or row.get("state") or row.get("Circle")
        if state:
            return str(state).replace(" Circle", "").strip()
    return ""


def calculate_cart_shipping(cart_items, address):
    origin_pincode = str(getattr(settings, "INDIA_POST_ORIGIN_PINCODE", "") or "").strip()
    if not origin_pincode:
        raise IndiaPostShippingError("INDIA_POST_ORIGIN_PINCODE is not configured on the server.")
    destination_pincode = str(getattr(address, "postal_code", "") or "").strip()
    weight = calculate_cart_weight_grams(cart_items)
    origin_state = getattr(settings, "INDIA_POST_ORIGIN_STATE", "")
    destination_state = "" if origin_pincode == destination_pincode else lookup_pincode_state(destination_pincode)
    quote = calculate_india_post_charge(
        weight_grams=weight,
        origin_pincode=origin_pincode,
        destination_pincode=destination_pincode,
        origin_state=origin_state,
        destination_state=destination_state,
        gst_rate=getattr(settings, "INDIA_POST_GST_RATE", "0"),
    )
    quote.update(
        {
            "origin_pincode": origin_pincode,
            "destination_pincode": destination_pincode,
            "estimated_delivery_time": getattr(settings, "INDIA_POST_ESTIMATED_DELIVERY", "4-5 business days"),
        }
    )
    return quote
