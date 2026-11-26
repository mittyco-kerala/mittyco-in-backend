"""Super-admin configuration and safe diagnostics for direct India Post."""

import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .india_post_fulfillment import IndiaPostDirectAPI, IndiaPostFulfillmentError
from .india_post_tariff import IndiaPostTariffClient, IndiaPostTariffError
from .models import IndiaPostBarcodeSeries
from .permissions import IsSuperAdmin
from .shipping_integration_config import (
    get_effective_shipping_config,
    save_shipping_config,
)


SETTING_FIELDS = {
    "fulfillment_provider": "SHIPPING_FULFILLMENT_PROVIDER",
    "direct_tariff_enabled": "INDIA_POST_DIRECT_TARIFF_ENABLED",
    "fulfillment_enabled": "INDIA_POST_FULFILLMENT_ENABLED",
    "live_booking_enabled": "INDIA_POST_LIVE_BOOKING_ENABLED",
    "auto_booking_enabled": "INDIA_POST_AUTO_BOOKING_ENABLED",
    "origin_pincode": "INDIA_POST_ORIGIN_PINCODE",
    "origin_state": "INDIA_POST_ORIGIN_STATE",
    "origin_latitude": "INDIA_POST_ORIGIN_LATITUDE",
    "origin_longitude": "INDIA_POST_ORIGIN_LONGITUDE",
    "free_delivery_radius_km": "INDIA_POST_FREE_DELIVERY_RADIUS_KM",
    "default_item_weight_grams": "INDIA_POST_DEFAULT_ITEM_WEIGHT_GRAMS",
    "tariff_service": "INDIA_POST_TARIFF_SERVICE",
    "parcel_length_cm": "INDIA_POST_PARCEL_LENGTH_CM",
    "parcel_width_cm": "INDIA_POST_PARCEL_WIDTH_CM",
    "parcel_height_cm": "INDIA_POST_PARCEL_HEIGHT_CM",
    "shape_of_article": "INDIA_POST_SHAPE_OF_ARTICLE",
    "bulk_customer_id": "INDIA_POST_BULK_CUSTOMER_ID",
    "sender_name": "INDIA_POST_SENDER_NAME",
    "sender_company": "INDIA_POST_SENDER_COMPANY",
    "sender_address_line1": "INDIA_POST_SENDER_ADDRESS_LINE1",
    "sender_address_line2": "INDIA_POST_SENDER_ADDRESS_LINE2",
    "sender_address_line3": "INDIA_POST_SENDER_ADDRESS_LINE3",
    "sender_city": "INDIA_POST_SENDER_CITY",
    "sender_state": "INDIA_POST_SENDER_STATE",
    "sender_pincode": "INDIA_POST_SENDER_PINCODE",
    "sender_mobile": "INDIA_POST_SENDER_MOBILE",
    "label_transmission_mode": "INDIA_POST_LABEL_TRANSMISSION_MODE",
}


class IndiaPostSettingsSerializer(serializers.Serializer):
    # Keep the existing route while DOP settings are staged; the view prevents
    # switching back to Prodinent after direct routing is activated.
    fulfillment_provider = serializers.ChoiceField(choices=("india_post", "prodinent"), required=False)
    direct_tariff_enabled = serializers.BooleanField(required=False)
    fulfillment_enabled = serializers.BooleanField(required=False)
    live_booking_enabled = serializers.BooleanField(required=False)
    auto_booking_enabled = serializers.BooleanField(required=False)
    origin_pincode = serializers.RegexField(r"^$|^\d{6}$", required=False, allow_blank=True)
    origin_state = serializers.CharField(required=False, allow_blank=True, max_length=80)
    origin_latitude = serializers.CharField(required=False, allow_blank=True, max_length=32)
    origin_longitude = serializers.CharField(required=False, allow_blank=True, max_length=32)
    free_delivery_radius_km = serializers.DecimalField(
        max_digits=4, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("5"), required=False
    )
    default_item_weight_grams = serializers.IntegerField(min_value=1, max_value=35000, required=False)
    tariff_service = serializers.ChoiceField(choices=("business_parcel",), required=False)
    parcel_length_cm = serializers.CharField(required=False, allow_blank=True, max_length=16)
    parcel_width_cm = serializers.CharField(required=False, allow_blank=True, max_length=16)
    parcel_height_cm = serializers.CharField(required=False, allow_blank=True, max_length=16)
    shape_of_article = serializers.ChoiceField(choices=("NROL", "ROLL"), required=False)
    bulk_customer_id = serializers.RegexField(r"^$|^\d{10}$", required=False, allow_blank=True)
    sender_name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    sender_company = serializers.CharField(required=False, allow_blank=True, max_length=80)
    sender_address_line1 = serializers.CharField(required=False, allow_blank=True, max_length=120)
    sender_address_line2 = serializers.CharField(required=False, allow_blank=True, max_length=120)
    sender_address_line3 = serializers.CharField(required=False, allow_blank=True, max_length=120)
    sender_city = serializers.CharField(required=False, allow_blank=True, max_length=80)
    sender_state = serializers.CharField(required=False, allow_blank=True, max_length=80)
    sender_pincode = serializers.RegexField(r"^$|^\d{6}$", required=False, allow_blank=True)
    sender_mobile = serializers.CharField(required=False, allow_blank=True, max_length=15)
    label_transmission_mode = serializers.ChoiceField(choices=("S", "A"), required=False)

    def validate(self, attrs):
        for name in ("origin_latitude", "origin_longitude"):
            if name in attrs and attrs[name]:
                try:
                    value = Decimal(attrs[name])
                except (InvalidOperation, TypeError):
                    raise serializers.ValidationError({name: "Enter a valid coordinate."})
                minimum, maximum = (Decimal("-90"), Decimal("90")) if name.endswith("latitude") else (Decimal("-180"), Decimal("180"))
                if not value.is_finite() or not minimum <= value <= maximum:
                    raise serializers.ValidationError({name: "Coordinate is outside the valid range."})
        latitude = attrs.get("origin_latitude")
        longitude = attrs.get("origin_longitude")
        if (latitude and not longitude) or (longitude and not latitude):
            raise serializers.ValidationError("Enter both store coordinates to enable the 5 km delivery radius.")
        for name in ("parcel_length_cm", "parcel_width_cm", "parcel_height_cm"):
            if name in attrs and attrs[name]:
                try:
                    value = Decimal(attrs[name])
                except (InvalidOperation, TypeError):
                    raise serializers.ValidationError({name: "Enter a valid parcel dimension."})
                if not value.is_finite() or value <= 0 or value > 150:
                    raise serializers.ValidationError({name: "Dimension must be greater than 0 and at most 150 cm."})
        return attrs


def _dashboard_settings():
    effective = get_effective_shipping_config()
    return {
        field: effective.get(key)
        for field, key in SETTING_FIELDS.items()
    }


def _valid_series(series):
    return bool(
        series.is_active
        and series.next_number <= series.last_number
        and series.allocation_start is not None
        and series.allocation_start <= series.next_number <= series.last_number
        and series.booking_office_id
        and series.booking_office_name
        and series.dropoff_pincode
        and re.fullmatch(r"\d{8}", series.booking_office_id)
        and re.fullmatch(r"\d{6}", series.dropoff_pincode)
    )


def _readiness(config):
    credentials = bool(
        str(getattr(settings, "INDIA_POST_API_USERNAME", "") or "").strip()
        and str(getattr(settings, "INDIA_POST_API_PASSWORD", "") or "")
    )
    dimensions = all(str(config.get(field) or "").strip() for field in (
        "parcel_length_cm", "parcel_width_cm", "parcel_height_cm"
    ))
    origin_pincode = str(config.get("origin_pincode") or "")
    tariff_ready = credentials and bool(re.fullmatch(r"\d{6}", origin_pincode)) and dimensions
    coordinates_ready = bool(config.get("origin_latitude") and config.get("origin_longitude"))
    sender_ready = all(str(config.get(field) or "").strip() for field in (
        "sender_name", "sender_company", "sender_address_line1", "sender_city",
        "sender_pincode", "sender_mobile",
    ))
    customer_id_ready = bool(re.fullmatch(r"\d{10}", str(config.get("bulk_customer_id") or "")))
    usable_series = any(
        _valid_series(series)
        for series in IndiaPostBarcodeSeries.objects.filter(article_type="BP")
    )
    booking_ready = credentials and dimensions and sender_ready and customer_id_ready and usable_series
    missing_weights = _missing_product_shipping_weights()
    return {
        "api_credentials_configured": credentials,
        "tariff_ready": tariff_ready,
        "five_km_delivery_ready": coordinates_ready,
        "sender_profile_ready": sender_ready,
        "bulk_customer_id_ready": customer_id_ready,
        "allocated_series_and_office_ready": usable_series,
        "booking_ready": booking_ready,
        "product_weights_ready": missing_weights == 0,
        "products_missing_shipping_weights": missing_weights,
        "auto_booking_ready": booking_ready and tariff_ready and missing_weights == 0,
    }


def _missing_product_shipping_weights():
    from .models import ProductVariantUnit, ProductVariant

    return (
        ProductVariant.objects.filter(
            price_type="single",
        ).filter(Q(shipping_weight_grams__isnull=True) | Q(shipping_weight_grams__lt=1)).count()
        + ProductVariantUnit.objects.filter(
            Q(shipping_weight_grams__isnull=True) | Q(shipping_weight_grams__lt=1),
        ).filter(
            Q(variant__shipping_weight_grams__isnull=True)
            | Q(variant__shipping_weight_grams__lt=1),
        ).count()
    )


def _config_to_model_values(config):
    return {
        SETTING_FIELDS[field]: str(value) if isinstance(value, Decimal) else value
        for field, value in config.items()
    }


def _settings_error(current_provider, updated, readiness):
    provider = updated.get("fulfillment_provider")
    if current_provider == "india_post" and provider != "india_post":
        return {"fulfillment_provider": "Direct India Post routing is active. Prodinent cannot be re-enabled from this page."}

    if provider == "india_post":
        if not updated.get("direct_tariff_enabled") or not readiness["tariff_ready"]:
            return {"direct_tariff_enabled": "Configure the live BP tariff before routing new orders to India Post."}
        if not readiness["five_km_delivery_ready"]:
            return {"origin_latitude": "Set the dispatch coordinates to apply the 5 km free-delivery rule."}
        if not updated.get("fulfillment_enabled") or not updated.get("live_booking_enabled"):
            return {"live_booking_enabled": "Enable India Post fulfilment and live booking before routing new orders."}
        if not readiness["booking_ready"]:
            return {"live_booking_enabled": "Complete sender details, DOP customer ID, allocated barcode range, and approved booking office first."}
        if not readiness["product_weights_ready"]:
            missing = readiness["products_missing_shipping_weights"]
            return {"fulfillment_provider": f"Set packed shipping weights for the {missing} product variant(s)/unit(s) before switching new orders to India Post."}

    if updated.get("live_booking_enabled"):
        if not updated.get("fulfillment_enabled"):
            return {"live_booking_enabled": "Enable India Post fulfilment first."}
        if not readiness["booking_ready"]:
            return {"live_booking_enabled": "Complete India Post credentials, sender details, parcel dimensions, approved barcode range, and booking office first."}
    if updated.get("auto_booking_enabled"):
        if not updated.get("live_booking_enabled") or not updated.get("direct_tariff_enabled") or not readiness["auto_booking_ready"]:
            return {"auto_booking_enabled": "Automatic booking needs direct BP tariff, live booking, and all booking setup marked Ready."}
    if updated.get("direct_tariff_enabled") and not readiness["tariff_ready"]:
        return {"direct_tariff_enabled": "Add working API credentials, the sender PIN code, and parcel dimensions before enabling live tariff quotes."}
    return None


class IndiaPostSettingsView(APIView):
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def get(self, request):
        config = _dashboard_settings()
        return Response({
            "settings": config,
            "readiness": _readiness(config),
            "provider_status": {
                "new_orders": "India Post direct" if config["fulfillment_provider"] == "india_post" else "Prodinent",
                "prodinent_historical_orders_retained": True,
                "india_post_api_credentials_configured": bool(
                    getattr(settings, "INDIA_POST_API_USERNAME", "")
                    and getattr(settings, "INDIA_POST_API_PASSWORD", "")
                ),
            },
        })

    def patch(self, request):
        serializer = IndiaPostSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        current = _dashboard_settings()
        updated = {**current, **serializer.validated_data}
        has_latitude = bool(str(updated.get("origin_latitude") or "").strip())
        has_longitude = bool(str(updated.get("origin_longitude") or "").strip())
        if has_latitude != has_longitude:
            return Response({"origin_latitude": "Enter both dispatch coordinates, or clear both."}, status=400)
        readiness = _readiness(updated)
        error = _settings_error(current.get("fulfillment_provider"), updated, readiness)
        if error:
            return Response(error, status=400)

        save_shipping_config(_config_to_model_values(updated), updated_by=request.user)
        return Response({"settings": updated, "readiness": _readiness(updated)})


class IndiaPostConnectionTestView(APIView):
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def post(self, request):
        try:
            IndiaPostTariffClient._access_token()
        except Exception:
            return Response({"success": False, "message": "India Post login failed. Check the server-side Customer Self-Service credentials."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"success": True, "message": "India Post login succeeded. No shipment was booked."})


class IndiaPostTariffTestView(APIView):
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def post(self, request):
        config = _dashboard_settings()
        destination = str(request.data.get("destination_pincode") or "").strip()
        if not re.fullmatch(r"\d{6}", destination):
            return Response({"destination_pincode": "Enter a six-digit destination PIN code."}, status=400)
        try:
            weight = int(request.data.get("weight_grams") or 500)
        except (TypeError, ValueError):
            return Response({"weight_grams": "Enter a valid weight in grams."}, status=400)
        if not 1 <= weight <= 35_000:
            return Response({"weight_grams": "Weight must be between 1 g and 35 kg."}, status=400)
        if not _readiness(config)["tariff_ready"]:
            return Response({"message": "Set the sender PIN and parcel dimensions first."}, status=409)
        try:
            quote = IndiaPostTariffClient.calculate_quote(
                service="business_parcel",
                weight_grams=weight,
                source_pincode=config["origin_pincode"],
                destination_pincode=destination,
                length_cm=config["parcel_length_cm"],
                width_cm=config["parcel_width_cm"],
                height_cm=config["parcel_height_cm"],
            )
        except (IndiaPostTariffError, ValueError, TypeError) as error:
            return Response({"success": False, "message": str(error)}, status=502)
        return Response({"success": True, "quote": quote, "message": "Live India Post tariff check completed. No shipment was booked."})


class IndiaPostOfficeSearchView(APIView):
    permission_classes = (IsAuthenticated, IsSuperAdmin)

    def get(self, request):
        try:
            offices = IndiaPostDirectAPI.search_post_offices(request.query_params.get("pincode"))
        except IndiaPostFulfillmentError as error:
            return Response({"message": str(error)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"offices": offices})
