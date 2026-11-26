"""Direct India Post production tariff API client.

This module only requests a shipping quote. Article booking remains on the
existing fulfillment integration until a separate migration is approved.
"""

import hashlib
import json
import logging
import time
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)


class IndiaPostTariffError(ValueError):
    """Raised when India Post cannot return a valid tariff quote."""


class IndiaPostTariffClient:
    TOKEN_REFRESH_MARGIN_SECONDS = 45

    @classmethod
    def _base_url(cls):
        base_url = str(getattr(settings, "INDIA_POST_API_BASE_URL", "") or "").strip().rstrip("/")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "app.indiapost.gov.in"
            or parsed.path.rstrip("/") != "/beextcustomer/v1"
        ):
            raise IndiaPostTariffError(
                "India Post production API URL must use the approved DOP host and base path."
            )
        return base_url

    @classmethod
    def _timeout(cls):
        try:
            timeout = float(getattr(settings, "INDIA_POST_API_TIMEOUT", 12))
        except (TypeError, ValueError):
            timeout = 12
        return min(max(timeout, 2), 30)

    @classmethod
    def _request_json(cls, path, *, method="GET", payload=None, token=None, query=None):
        url = f"{cls._base_url()}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=cls._timeout()) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            logger.warning("India Post API returned HTTP %s for %s", error.code, path)
            raise IndiaPostTariffError(
                f"India Post tariff service is unavailable (HTTP {error.code})."
            ) from None
        except (URLError, TimeoutError, OSError) as error:
            logger.warning("India Post API request failed for %s: %s", path, type(error).__name__)
            raise IndiaPostTariffError("India Post tariff service is unavailable.") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise IndiaPostTariffError("India Post returned an unreadable API response.") from None
        if not isinstance(result, dict):
            raise IndiaPostTariffError("India Post returned an invalid API response.")
        return result

    @classmethod
    def _token_cache_key(cls):
        username = str(getattr(settings, "INDIA_POST_API_USERNAME", "") or "").strip()
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]
        return f"india-post-api-token:{digest}"

    @classmethod
    def _token_data(cls, response):
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        if response.get("success") is False:
            raise IndiaPostTariffError("India Post rejected API authentication.")
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise IndiaPostTariffError("India Post authentication returned no access token.")
        try:
            expires_in = max(int(data.get("expires_in") or 900), 60)
            refresh_expires_in = max(int(data.get("refresh_expires_in") or expires_in), 60)
        except (TypeError, ValueError):
            expires_in = refresh_expires_in = 900
        return {
            "access_token": access_token,
            "refresh_token": str(data.get("refresh_token") or "").strip(),
            "access_expires_at": time.time() + expires_in,
            "refresh_expires_at": time.time() + refresh_expires_in,
            "cache_seconds": max(refresh_expires_in - 60, 60),
        }

    @classmethod
    def _login(cls):
        username = str(getattr(settings, "INDIA_POST_API_USERNAME", "") or "").strip()
        password = str(getattr(settings, "INDIA_POST_API_PASSWORD", "") or "")
        if not username or not password:
            raise IndiaPostTariffError(
                "India Post API credentials are not configured on the server."
            )
        response = cls._request_json(
            "/access/login",
            method="POST",
            payload={"username": username, "password": password},
        )
        return cls._token_data(response)

    @classmethod
    def _access_token(cls):
        cached = cache.get(cls._token_cache_key()) or {}
        if cached.get("access_token") and cached.get("access_expires_at", 0) > (
            time.time() + cls.TOKEN_REFRESH_MARGIN_SECONDS
        ):
            return cached["access_token"]

        bundle = None
        if cached.get("refresh_token") and cached.get("refresh_expires_at", 0) > time.time():
            try:
                refreshed = cls._request_json(
                    "/access/TokenWithRtoken",
                    method="POST",
                    token=cached["refresh_token"],
                )
                bundle = cls._token_data(refreshed)
                if not bundle.get("refresh_token"):
                    bundle["refresh_token"] = cached["refresh_token"]
            except IndiaPostTariffError:
                logger.info("India Post refresh token expired; requesting a new session")

        if bundle is None:
            bundle = cls._login()

        cache.set(
            cls._token_cache_key(),
            {key: value for key, value in bundle.items() if key != "cache_seconds"},
            timeout=bundle["cache_seconds"],
        )
        return bundle["access_token"]

    @staticmethod
    def _positive_decimal(value, label):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise IndiaPostTariffError(f"{label} must be a positive number.") from None
        if not number.is_finite() or number <= 0:
            raise IndiaPostTariffError(f"{label} must be a positive number.")
        return number

    @staticmethod
    def _format_decimal(value):
        return format(value.normalize(), "f")

    @classmethod
    def calculate_quote(
        cls,
        *,
        service,
        weight_grams,
        source_pincode,
        destination_pincode,
        length_cm,
        width_cm,
        height_cm,
    ):
        service = str(service or "").strip().lower()
        if service not in {"business_parcel", "speed_post"}:
            raise IndiaPostTariffError(
                "Choose the India Post tariff service approved for the contract."
            )
        try:
            weight = int(weight_grams)
        except (TypeError, ValueError):
            raise IndiaPostTariffError("Packed parcel weight must be a whole number of grams.") from None
        if weight < 1 or weight > 35_000:
            raise IndiaPostTariffError("Packed parcel weight must be between 1 g and 35 kg.")

        source = str(source_pincode or "").strip()
        destination = str(destination_pincode or "").strip()
        if not (source.isdigit() and len(source) == 6 and destination.isdigit() and len(destination) == 6):
            raise IndiaPostTariffError("Valid six-digit source and delivery PIN codes are required.")

        dimensions = {
            "length": cls._positive_decimal(length_cm, "Parcel length"),
            "width": cls._positive_decimal(width_cm, "Parcel width"),
            "height": cls._positive_decimal(height_cm, "Parcel height"),
        }
        query = {
            "product-code": "BP" if service == "business_parcel" else "SP",
            "weight": str(weight),
            "source-pincode": source,
            "destination-pincode": destination,
            **{name: cls._format_decimal(value) for name, value in dimensions.items()},
        }
        if service == "business_parcel":
            path = "/business-parcel-tariff/calculate"
            query["ins"] = "0"
            display_name = "India Post Business Parcel (API)"
        else:
            path = "/speed-post/tariffs"
            query["INS"] = "0"
            query["POD"] = "NO"
            display_name = "India Post Speed Post (API)"

        response = cls._request_json(path, query=query, token=cls._access_token())
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        if data.get("success") is False or response.get("success") is False:
            raise IndiaPostTariffError("India Post could not calculate this parcel tariff.")
        try:
            amount = Decimal(
                str(data.get("total_with_tax", data.get("final_amount")))
            )
        except (KeyError, InvalidOperation, TypeError, ValueError):
            raise IndiaPostTariffError(
                "India Post response did not contain a valid total tariff."
            ) from None
        if not amount.is_finite() or amount < 0:
            raise IndiaPostTariffError("India Post returned an invalid tariff amount.")

        try:
            base_amount = Decimal(str(data.get("base_tariff", data.get("price", amount))))
            tax_amount = Decimal(str(data.get("gst", data.get("total_tax", 0))))
        except (InvalidOperation, TypeError, ValueError):
            raise IndiaPostTariffError("India Post returned invalid tariff details.") from None
        if not base_amount.is_finite() or not tax_amount.is_finite():
            raise IndiaPostTariffError("India Post returned invalid tariff details.")

        chargeable_weight = data.get("chargeable_weight", weight)
        try:
            chargeable_weight = int(chargeable_weight)
        except (TypeError, ValueError):
            chargeable_weight = weight

        return {
            "amount": str(amount.quantize(Decimal("0.01"))),
            "base_amount": str(base_amount.quantize(Decimal("0.01"))),
            "tax_amount": str(tax_amount.quantize(Decimal("0.01"))),
            "weight_grams": weight,
            "chargeable_weight_grams": chargeable_weight,
            "volumetric_weight_grams": data.get("volumetric_weight"),
            "shipping_class": "INDIA_POST_API",
            "rate_version": "india_post_live_api",
            "tariff_source": "india_post_api",
            "service": display_name,
            "gst_rate": "api_calculated",
        }
