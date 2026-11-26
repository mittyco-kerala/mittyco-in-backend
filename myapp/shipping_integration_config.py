"""Database-backed operational settings for the super-admin shipping dashboard.

Credentials and API tokens deliberately remain in server environment variables.
Only non-secret shipping controls are stored in the database.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import OperationalError, ProgrammingError

from .models import ShippingIntegrationConfig


DASHBOARD_SETTING_KEYS = (
    "SHIPPING_FULFILLMENT_PROVIDER",
    "INDIA_POST_DIRECT_TARIFF_ENABLED",
    "INDIA_POST_FULFILLMENT_ENABLED",
    "INDIA_POST_LIVE_BOOKING_ENABLED",
    "INDIA_POST_AUTO_BOOKING_ENABLED",
    "INDIA_POST_ORIGIN_PINCODE",
    "INDIA_POST_ORIGIN_STATE",
    "INDIA_POST_ORIGIN_LATITUDE",
    "INDIA_POST_ORIGIN_LONGITUDE",
    "INDIA_POST_FREE_DELIVERY_RADIUS_KM",
    "INDIA_POST_DEFAULT_ITEM_WEIGHT_GRAMS",
    "INDIA_POST_TARIFF_SERVICE",
    "INDIA_POST_PARCEL_LENGTH_CM",
    "INDIA_POST_PARCEL_WIDTH_CM",
    "INDIA_POST_PARCEL_HEIGHT_CM",
    "INDIA_POST_SHAPE_OF_ARTICLE",
    "INDIA_POST_BULK_CUSTOMER_ID",
    "INDIA_POST_SENDER_NAME",
    "INDIA_POST_SENDER_COMPANY",
    "INDIA_POST_SENDER_ADDRESS_LINE1",
    "INDIA_POST_SENDER_ADDRESS_LINE2",
    "INDIA_POST_SENDER_ADDRESS_LINE3",
    "INDIA_POST_SENDER_CITY",
    "INDIA_POST_SENDER_STATE",
    "INDIA_POST_SENDER_PINCODE",
    "INDIA_POST_SENDER_MOBILE",
    "INDIA_POST_LABEL_TRANSMISSION_MODE",
)
_OVERRIDES_CACHE_KEY = "myapp:shipping-integration-config:v1"
_UNSET = object()


def _dashboard_overrides():
    values = cache.get(_OVERRIDES_CACHE_KEY, _UNSET)
    if values is not _UNSET:
        return values
    try:
        values = (
            ShippingIntegrationConfig.objects.filter(pk=1)
            .values_list("values", flat=True)
            .first()
        )
    except (OperationalError, ProgrammingError):
        values = {}
    if not isinstance(values, dict):
        values = {}
    cache.set(_OVERRIDES_CACHE_KEY, values, timeout=3)
    return values


def get_shipping_setting(name, default=None):
    """Return the dashboard override, falling back to the server environment."""

    fallback = getattr(settings, name, default)
    if name not in DASHBOARD_SETTING_KEYS:
        return fallback

    values = _dashboard_overrides()
    if isinstance(values, dict) and name in values:
        return values[name]
    return fallback


def get_effective_shipping_config():
    return {name: get_shipping_setting(name) for name in DASHBOARD_SETTING_KEYS}


def save_shipping_config(values, *, updated_by=None):
    from .models import ShippingIntegrationConfig

    instance, _ = ShippingIntegrationConfig.objects.get_or_create(pk=1)
    instance.values = values
    instance.updated_by = updated_by
    instance.save(update_fields=("values", "updated_by", "updated_at"))
    cache.delete(_OVERRIDES_CACHE_KEY)
    return instance


def prodinent_is_enabled_for_new_actions():
    """Prodinent actions stop when dashboard routing is set to direct DOP."""

    return (
        get_shipping_setting("SHIPPING_FULFILLMENT_PROVIDER", "prodinent")
        == "prodinent"
        and bool(getattr(settings, "PRODINENT_ENABLED", False))
    )
