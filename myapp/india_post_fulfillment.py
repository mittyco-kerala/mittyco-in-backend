"""Direct India Post BP booking, label, barcode, and tracking operations.

Authentication is shared with the direct tariff client. Booking remains
disabled unless both the integration and live-write switches are enabled.
"""

import logging
import re
import textwrap
from types import SimpleNamespace
from decimal import Decimal, InvalidOperation

import requests

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .india_post_tariff import IndiaPostTariffClient
from .models import IndiaPostBarcodeSeries, Order, ProductVariant


logger = logging.getLogger(__name__)


class IndiaPostFulfillmentError(RuntimeError):
    def __init__(self, message, *, status_code=None, outcome_unknown=False):
        super().__init__(message)
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown


class IndiaPostDirectAPI:
    """Small API boundary for the India Post production integration."""

    @classmethod
    def _request_json(cls, path, *, method="GET", payload=None, query=None):
        url = f"{IndiaPostTariffClient._base_url()}/{path.lstrip('/')}"
        token = IndiaPostTariffClient._access_token()
        for attempt in range(2):
            try:
                response = requests.request(
                    method,
                    url,
                    params=query,
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    timeout=IndiaPostTariffClient._timeout(),
                )
            except requests.RequestException as error:
                raise IndiaPostFulfillmentError(
                    "India Post could not be reached.",
                    outcome_unknown=method.upper() == "POST",
                ) from error

            if response.status_code == 401 and attempt == 0:
                cache.delete(IndiaPostTariffClient._token_cache_key())
                token = IndiaPostTariffClient._access_token()
                continue
            if not response.ok:
                raise IndiaPostFulfillmentError(
                    f"India Post rejected the request (HTTP {response.status_code}).",
                    status_code=response.status_code,
                    outcome_unknown=(method.upper() == "POST" and response.status_code >= 500),
                )
            try:
                result = response.json()
            except ValueError as error:
                raise IndiaPostFulfillmentError(
                    "India Post returned an unreadable response.",
                    outcome_unknown=method.upper() == "POST",
                ) from error
            if not isinstance(result, (dict, list)):
                raise IndiaPostFulfillmentError(
                    "India Post returned an invalid response.",
                    outcome_unknown=method.upper() == "POST",
                )
            return result
        raise IndiaPostFulfillmentError("India Post authentication failed.")

    @classmethod
    def search_post_offices(cls, pincode):
        pincode = str(pincode or "").strip()
        if not re.fullmatch(r"\d{6}", pincode):
            raise IndiaPostFulfillmentError("Enter a valid 6-digit PIN code.")
        result = cls._request_json(
            "/pincode-search",
            query={"pincode": pincode, "office-type": "post"},
        )
        if not isinstance(result, list):
            raise IndiaPostFulfillmentError("India Post returned an invalid office list.")
        return [
            {
                "office_id": str(row.get("office_id") or ""),
                "office_name": str(row.get("office_name") or ""),
                "office_type_code": str(row.get("office_type_code") or ""),
                "pincode": str(row.get("pincode") or pincode),
                "state_name": str(row.get("state_name") or ""),
                "city_name": str(row.get("city_name") or ""),
            }
            for row in result
            if isinstance(row, dict)
            and row.get("delivery_office_flag") is True
            and str(row.get("office_type_code") or "").upper() != "BPO"
        ]

    @classmethod
    def book_article(cls, customer_id, article):
        if not (
            getattr(settings, "INDIA_POST_FULFILLMENT_ENABLED", False)
            and getattr(settings, "INDIA_POST_LIVE_BOOKING_ENABLED", False)
        ):
            raise IndiaPostFulfillmentError("India Post live booking is disabled.")
        if not re.fullmatch(r"\d{10}", str(customer_id or "")):
            raise IndiaPostFulfillmentError("India Post bulk customer ID is not configured.")
        return cls._request_json(
            f"/process-articles/{customer_id}",
            method="POST",
            payload={"articles": [article]},
        )

    @classmethod
    def tracking(cls, barcodes):
        if not getattr(settings, "INDIA_POST_FULFILLMENT_ENABLED", False):
            raise IndiaPostFulfillmentError("India Post fulfilment is disabled.")
        if not barcodes or len(barcodes) > 500:
            raise IndiaPostFulfillmentError("Tracking accepts 1 to 500 article barcodes.")
        return cls._request_json(
            "/tracking/bulk",
            method="POST",
            payload={"bulk": list(barcodes)},
        )

    @classmethod
    def create_label(cls, label_payload):
        if not getattr(settings, "INDIA_POST_FULFILLMENT_ENABLED", False):
            raise IndiaPostFulfillmentError("India Post fulfilment is disabled.")
        url = f"{IndiaPostTariffClient._base_url()}/label/create/domestic"
        token = IndiaPostTariffClient._access_token()
        try:
            response = requests.post(
                url,
                json=[label_payload],
                headers={
                    "Accept": "application/pdf",
                    "Authorization": f"Bearer {token}",
                },
                timeout=IndiaPostTariffClient._timeout(),
            )
        except requests.RequestException as error:
            raise IndiaPostFulfillmentError("India Post label service is unavailable.") from error
        if not response.ok:
            raise IndiaPostFulfillmentError(
                f"India Post could not create the label (HTTP {response.status_code}).",
                status_code=response.status_code,
            )
        if not response.content.startswith(b"%PDF"):
            raise IndiaPostFulfillmentError("India Post did not return a PDF label.")
        return response.content


def _required_setting(name, label):
    value = str(getattr(settings, name, "") or "").strip()
    if not value:
        raise IndiaPostFulfillmentError(f"Configure {label} on the backend first.")
    return value


def _mobile_number(value, label):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 10:
        digits = digits[-10:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise IndiaPostFulfillmentError(f"A valid 10-digit {label} is required.")
    return digits


def _address_lines(value, label):
    raw_lines = [line.strip() for line in str(value or "").replace("\r", "").split("\n")]
    chunks = []
    for line in raw_lines:
        if not line:
            continue
        wrapped = textwrap.wrap(line, width=80, break_long_words=False, break_on_hyphens=False)
        if not wrapped:
            continue
        chunks.extend(wrapped)
    if not chunks or len(chunks) > 3 or sum(len(line) for line in chunks) > 240:
        raise IndiaPostFulfillmentError(
            f"{label} must fit within three address lines (80 characters per line)."
        )
    return chunks + [""] * (3 - len(chunks))


def _parcel_dimensions():
    dimensions = {}
    for field, setting_name, label in (
        ("length", "INDIA_POST_PARCEL_LENGTH_CM", "parcel length"),
        ("breadth_diameter", "INDIA_POST_PARCEL_WIDTH_CM", "parcel width"),
        ("height", "INDIA_POST_PARCEL_HEIGHT_CM", "parcel height"),
    ):
        raw = str(getattr(settings, setting_name, "") or "").strip()
        try:
            value = Decimal(raw)
        except (InvalidOperation, TypeError, ValueError):
            raise IndiaPostFulfillmentError(f"Configure the {label} in centimetres.") from None
        if not value.is_finite() or value <= 0 or value > 150:
            raise IndiaPostFulfillmentError(f"The {label} must be greater than 0 and at most 150 cm.")
        dimensions[field] = format(value.normalize(), "f")
    return dimensions


def _order_weight_grams(order):
    total = 0
    for item in order.items.select_related(
        "product", "color", "variant_unit", "variant_unit__variant"
    ):
        variant = item.variant_unit.variant if item.variant_unit_id else ProductVariant.objects.filter(
            product_id=item.product_id,
            color_id=item.color_id,
        ).order_by("id").first()
        weight = (
            item.variant_unit.shipping_weight_grams
            if item.variant_unit_id
            else None
        )
        if weight is None and variant:
            weight = variant.shipping_weight_grams
        if not weight or int(weight) < 1:
            raise IndiaPostFulfillmentError(
                f"Packed shipping weight is missing for {item.product.name}. Set it in the product dashboard first."
            )
        total += int(weight) * int(item.quantity)
    if total < 1 or total > 35_000:
        raise IndiaPostFulfillmentError("The packed order weight must be between 1 g and 35 kg.")
    return total


def _sender_profile():
    name = _required_setting("INDIA_POST_SENDER_NAME", "the sender name")
    company = _required_setting("INDIA_POST_SENDER_COMPANY", "the sender/company name")
    city = _required_setting("INDIA_POST_SENDER_CITY", "the sender city")
    pincode = _required_setting("INDIA_POST_SENDER_PINCODE", "the sender PIN code")
    if not re.fullmatch(r"\d{6}", pincode):
        raise IndiaPostFulfillmentError("The sender PIN code must have 6 digits.")
    mobile = _mobile_number(
        _required_setting("INDIA_POST_SENDER_MOBILE", "the sender mobile number"),
        "sender mobile number",
    )
    address = "\n".join(
        value
        for value in (
            str(getattr(settings, "INDIA_POST_SENDER_ADDRESS_LINE1", "") or "").strip(),
            str(getattr(settings, "INDIA_POST_SENDER_ADDRESS_LINE2", "") or "").strip(),
            str(getattr(settings, "INDIA_POST_SENDER_ADDRESS_LINE3", "") or "").strip(),
        )
        if value
    )
    lines = _address_lines(address, "Sender address")
    return {
        "name": name[:80],
        "company": company[:80],
        "address_lines": lines,
        "city": city[:80],
        "state": str(getattr(settings, "INDIA_POST_SENDER_STATE", "") or "").strip()[:80],
        "pincode": pincode,
        "mobile": mobile,
    }


def _recipient_profile(order):
    address = order.address
    if not address:
        raise IndiaPostFulfillmentError("The order has no delivery address.")
    name = str(address.full_name or "").strip()
    city = str(address.city or "").strip()
    pincode = str(address.postal_code or "").strip()
    if not name or len(name) > 80:
        raise IndiaPostFulfillmentError("The recipient name is missing or too long.")
    if not city:
        raise IndiaPostFulfillmentError("The recipient city is required for India Post booking.")
    if not re.fullmatch(r"\d{6}", pincode):
        raise IndiaPostFulfillmentError("The recipient PIN code must have 6 digits.")
    mobile = _mobile_number(address.phone, "recipient mobile number")
    lines = _address_lines(address.address_line, "Recipient address")
    return {
        "name": name,
        "address_lines": lines,
        "city": city[:80],
        "pincode": pincode,
        "mobile": mobile,
    }


def build_bp_booking_payload(order, barcode, series):
    """Build the single-article payload documented by CEPT for Business Parcel."""

    if order.payment_method == "COD":
        raise IndiaPostFulfillmentError(
            "India Post BP COD tariff fields are not confirmed in the supplied API document; use prepaid payment until CEPT confirms them."
        )
    sender = _sender_profile()
    recipient = _recipient_profile(order)
    weight = _order_weight_grams(order)
    dimensions = _parcel_dimensions()
    bulk_customer_id = str(
        getattr(settings, "INDIA_POST_BULK_CUSTOMER_ID", "")
        or getattr(settings, "INDIA_POST_API_USERNAME", "")
        or ""
    ).strip()
    if not re.fullmatch(r"\d{10}", bulk_customer_id):
        raise IndiaPostFulfillmentError("Configure the 10-digit India Post bulk customer ID.")
    if not re.fullmatch(r"[A-Z]{2}\d{9}IN", str(barcode or "")):
        raise IndiaPostFulfillmentError("The DOP-allocated article barcode is invalid.")
    office_id = str(getattr(series, "booking_office_id", "") or "").strip()
    office_name = str(getattr(series, "booking_office_name", "") or "").strip()
    dropoff_pincode = str(getattr(series, "dropoff_pincode", "") or "").strip()
    if not re.fullmatch(r"\d{8}", office_id) or not office_name or not re.fullmatch(r"\d{6}", dropoff_pincode):
        raise IndiaPostFulfillmentError(
            "Add the DOP booking office ID, office name, and drop-off PIN to the barcode series before booking."
        )

    shape = str(getattr(settings, "INDIA_POST_SHAPE_OF_ARTICLE", "NROL") or "NROL").upper()
    if shape not in {"NROL", "ROLL"}:
        raise IndiaPostFulfillmentError("Business Parcel shape must be NROL or ROLL.")

    return {
        "bulk_customer_id": bulk_customer_id,
        "contract_id": series.contract_id,
        "barcode_no": barcode,
        "pickup_or_dropoff": "DROPOFF",
        "pickup_dropoff_office_id": int(office_id),
        "article_type": "BP",
        "physical_weight": weight,
        "shape_of_article": shape,
        "length": dimensions["length"],
        "breadth_diameter": dimensions["breadth_diameter"],
        "height": dimensions["height"],
        "priority_flag": "FALSE",
        "delivery_instruction": "",
        "delivery_slot": "",
        "instruction_rts": "",
        "sender_name": sender["name"],
        "sender_company": sender["company"],
        "sender_add_line_1": sender["address_lines"][0],
        "sender_add_line_2": sender["address_lines"][1],
        "sender_add_line_3": sender["address_lines"][2],
        "sender_city": sender["city"],
        "sender_state": sender["state"],
        "sender_pincode": sender["pincode"],
        "sender_emailid": "",
        "sender_alt_contact": "",
        "sender_kyc": "",
        "sender_tax_reference": "",
        "receiver_name": recipient["name"],
        "receiver_company": "",
        "receiver_add_line_1": recipient["address_lines"][0],
        "receiver_add_line_2": recipient["address_lines"][1],
        "receiver_add_line_3": recipient["address_lines"][2],
        "receiver_city": recipient["city"],
        "receiver_pincode": recipient["pincode"],
        "receiver_emailid": str(order.user.email or "")[:80],
        "receiver_alt_contact": "",
        "receiver_kyc": "",
        "receiver_tax_reference": "",
        "alt_address_flag": "FALSE",
        "pickup_address_flag": "FALSE",
        "drop_off_pincode": dropoff_pincode,
        "sender_mobile_no": sender["mobile"],
        "receiver_mobile_no": recipient["mobile"],
        "prepayment_code": "",
        "value_of_prepayment": 0,
        "codr_cod": "",
        "value_for_codr_cod": "",
        "insurance_type": "",
        "value_of_insurance": 0,
        "ack": "FALSE",
        "reg": "FALSE",
        "otp": "FALSE",
        "bulk_reference": f"ORD-{order.id:06d}",
        "pickup_address_id": "",
        "pickup_addressee_name": "",
        "pickup_company_name": "",
        "pickup_address_line1": "",
        "pickup_address_line2": "",
        "pickup_address_line3": "",
        "pickup_city": "",
        "pickup_state": "",
        "pickup_pincode": "",
        "pickup_email_id": "",
        "pickup_alt_contact_no": "",
        "pickup_mobile_no": "",
        "pickup_schedule_slot": "",
        "pickup_schedule_date": "",
        "alt_addressee_name": "",
        "alt_company_name": "",
        "alt_address_line1": "",
        "alt_address_line2": "",
        "alt_address_line3": "",
        "alt_city": "",
        "alt_state": "",
        "alt_pincode": "",
        "alt_email_id": "",
        "alt_contact_no": "",
        "alt_alternate_mobile_no": "",
    }


def _claim_barcode(order_id, series_id=None):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.india_post_booking_status in {"Booking", "Needs review", "Booked"}:
            if order.india_post_booking_status == "Booked":
                return order, order.india_post_barcode, None
            raise IndiaPostFulfillmentError(
                "A previous booking may have reached India Post. Check DOP before retrying."
            )
        if order.india_post_barcode:
            if not all(
                (
                    order.india_post_contract_id,
                    order.india_post_booking_office_id,
                    order.india_post_booking_office_name,
                    order.india_post_dropoff_pincode,
                )
            ):
                raise IndiaPostFulfillmentError(
                    "The previous barcode lacks its original office/contract details; reconcile it in DOP before retrying."
                )
            context = SimpleNamespace(
                contract_id=order.india_post_contract_id,
                booking_office_id=order.india_post_booking_office_id,
                booking_office_name=order.india_post_booking_office_name,
                dropoff_pincode=order.india_post_dropoff_pincode,
            )
            order.india_post_booking_status = "Booking"
            order.india_post_booking_attempted_at = timezone.now()
            order.india_post_last_error = ""
            order.save(
                update_fields=(
                    "india_post_booking_status",
                    "india_post_booking_attempted_at",
                    "india_post_last_error",
                    "updated_at",
                )
            )
            return order, order.india_post_barcode, context
        series_query = IndiaPostBarcodeSeries.objects.select_for_update().filter(
            is_active=True, article_type="BP", next_number__lte=F("last_number")
        )
        if series_id:
            series = series_query.filter(pk=series_id).first()
        else:
            series = series_query.order_by("created_at", "id").first()
        if not series:
            raise IndiaPostFulfillmentError(
                "No active Business Parcel barcode series has unused numbers. Add or activate an India Post allocated range."
            )
        try:
            series.full_clean()
        except ValidationError as error:
            raise IndiaPostFulfillmentError("The active India Post barcode series is invalid.") from error
        if series.next_number > series.last_number:
            raise IndiaPostFulfillmentError("The active India Post barcode series is exhausted.")
        barcode = f"{series.barcode_prefix}{series.next_number:09d}IN"
        if Order.objects.filter(india_post_barcode=barcode).exclude(pk=order.pk).exists():
            raise IndiaPostFulfillmentError("This barcode is already assigned to another order.")
        series.next_number += 1
        series.save(update_fields=("next_number", "updated_at"))
        order.india_post_barcode = barcode
        order.india_post_booking_status = "Booking"
        order.india_post_booking_attempted_at = timezone.now()
        order.india_post_contract_id = series.contract_id
        order.india_post_booking_office_id = series.booking_office_id
        order.india_post_booking_office_name = series.booking_office_name
        order.india_post_dropoff_pincode = series.dropoff_pincode
        order.india_post_last_error = ""
        order.save(
            update_fields=(
                "india_post_barcode",
                "india_post_booking_status",
                "india_post_booking_attempted_at",
                "india_post_contract_id",
                "india_post_booking_office_id",
                "india_post_booking_office_name",
                "india_post_dropoff_pincode",
                "india_post_last_error",
                "updated_at",
            )
        )
        return order, barcode, series


def _finish_booking(order_id, *, booking_status, error="", reference=""):
    values = {
        "india_post_booking_status": booking_status,
        "india_post_last_error": str(error or "")[:500],
    }
    if reference:
        values["india_post_booking_reference"] = str(reference)[:80]
    if booking_status == "Booked":
        values["india_post_booked_at"] = timezone.now()
    Order.objects.filter(pk=order_id).update(**values, updated_at=timezone.now())


def book_local_order_in_india_post(order_id):
    """Book one paid BP order, using a DOP-allocated barcode exactly once."""

    if not getattr(settings, "INDIA_POST_FULFILLMENT_ENABLED", False):
        raise IndiaPostFulfillmentError("India Post fulfilment is disabled.")
    if not getattr(settings, "INDIA_POST_LIVE_BOOKING_ENABLED", False):
        raise IndiaPostFulfillmentError("India Post live booking is disabled.")

    order = Order.objects.select_related("address", "user").get(pk=order_id)
    if order.fulfillment_provider != "india_post":
        raise IndiaPostFulfillmentError("This order is assigned to a different fulfilment provider.")
    if order.payment_status != "Paid":
        raise IndiaPostFulfillmentError("Only paid orders can be booked with India Post.")
    if order.prodinent_order_id or order.prodinent_article_id:
        raise IndiaPostFulfillmentError("This order already has a Prodinent shipment; duplicate booking is blocked.")
    quote = order.shipping_quote if isinstance(order.shipping_quote, dict) else {}
    if quote.get("free_delivery") or quote.get("tariff_source") != "india_post_api":
        raise IndiaPostFulfillmentError(
            "This order does not have a paid India Post API quote; local free-delivery orders are not sent to DOP."
        )
    if order.india_post_booking_status in {"Booking", "Needs review", "Booked"}:
        if order.india_post_booking_status == "Booked":
            return {"barcode": order.india_post_barcode, "duplicate": True}
        raise IndiaPostFulfillmentError(
            "A previous booking may have reached India Post. Check the barcode in DOP before retrying."
        )

    if order.india_post_barcode:
        series = SimpleNamespace(
            contract_id=order.india_post_contract_id,
            booking_office_id=order.india_post_booking_office_id,
            booking_office_name=order.india_post_booking_office_name,
            dropoff_pincode=order.india_post_dropoff_pincode,
        )
        if not all((series.contract_id, series.booking_office_id, series.dropoff_pincode)):
            raise IndiaPostFulfillmentError("The saved DOP barcode details need reconciliation.")
        series_id = None
    else:
        series = IndiaPostBarcodeSeries.objects.filter(
            is_active=True, article_type="BP"
        ).order_by("created_at", "id").first()
        if not series:
            raise IndiaPostFulfillmentError(
                "Add the barcode range allocated by India Post and its approved drop-off office first."
            )
        series_id = series.pk
    # Validate address, packed weight, dimensions, and sender config before
    # reserving a barcode from the scarce DOP-allocated range.
    build_bp_booking_payload(order, "AA100000000IN", series)
    order, barcode, series = _claim_barcode(order.id, series_id=series_id)
    if not barcode:
        return {"barcode": "", "duplicate": True}
    payload = build_bp_booking_payload(order, barcode, series)
    try:
        response = IndiaPostDirectAPI.book_article(payload["bulk_customer_id"], payload)
    except IndiaPostFulfillmentError as error:
        state = "Needs review" if error.outcome_unknown else "Rejected"
        _finish_booking(order.id, booking_status=state, error=str(error))
        logger.warning(
            "India Post BP booking failed for order %s (HTTP %s, outcome_unknown=%s)",
            order.id,
            error.status_code,
            error.outcome_unknown,
        )
        raise

    if not isinstance(response, dict):
        _finish_booking(
            order.id,
            booking_status="Needs review",
            error="India Post returned an unreadable booking result.",
        )
        raise IndiaPostFulfillmentError(
            "India Post returned an unreadable booking result.", outcome_unknown=True
        )
    valid_articles = response.get("valid_articles") or []
    error_articles = response.get("error_articles") or []
    valid_match = next(
        (row for row in valid_articles if isinstance(row, dict) and row.get("barcode_no") == barcode),
        None,
    )
    error_match = next(
        (row for row in error_articles if isinstance(row, dict) and row.get("barcode_no") == barcode),
        None,
    )
    if valid_match:
        reference = (
            response.get("mail_booking_dom_id")
            or response.get("correlation_id")
            or response.get("batch_id")
            or ""
        )
        _finish_booking(order.id, booking_status="Booked", reference=reference)
        return {"barcode": barcode, "booking_reference": str(reference), "duplicate": False}
    if error_match or response.get("success") is False:
        errors = error_match.get("errors") if isinstance(error_match, dict) else None
        message = "; ".join(str(value) for value in errors or []) or str(
            response.get("message") or "India Post rejected this article."
        )
        _finish_booking(order.id, booking_status="Rejected", error=message)
        raise IndiaPostFulfillmentError(message)

    _finish_booking(
        order.id,
        booking_status="Needs review",
        error="India Post response did not confirm whether this barcode was booked.",
    )
    raise IndiaPostFulfillmentError(
        "India Post response did not confirm the booking. Check DOP before retrying.",
        outcome_unknown=True,
    )


def _tracking_event_list(record):
    details = record.get("tracking_details")
    if not isinstance(details, list):
        return []
    events = []
    for event in details:
        if not isinstance(event, dict):
            continue
        events.append(
            {
                "date": str(event.get("date") or "")[:40],
                "time": str(event.get("time") or "")[:20],
                "office": str(event.get("office") or "")[:100],
                "event": str(event.get("event") or "")[:120],
                "remarks": str(event.get("remarks") or "")[:200],
                "rts": bool(event.get("rts")),
            }
        )
    return events[:50]


def _local_status_from_india_post(record, events, current_status):
    delivery = record.get("del_status")
    delivery = delivery.get("del_status") if isinstance(delivery, dict) else delivery
    if "deliver" in str(delivery or "").casefold() and "not delivered" not in str(delivery).casefold():
        return "Delivered"
    latest = str(events[0].get("event") if events else "").casefold()
    if any(term in latest for term in ("dispatched", "transit", "taken out for delivery", "out for delivery")):
        return "Shipped"
    return current_status


def refresh_local_order_india_post_tracking(order_id):
    order = Order.objects.get(pk=order_id)
    if order.fulfillment_provider != "india_post" or not order.india_post_barcode:
        raise IndiaPostFulfillmentError("This order has no India Post article barcode to track.")
    response = IndiaPostDirectAPI.tracking([order.india_post_barcode])
    records = response.get("data") if isinstance(response, dict) else None
    if not isinstance(records, list):
        raise IndiaPostFulfillmentError("India Post returned an invalid tracking response.")
    record = next(
        (
            row for row in records
            if isinstance(row, dict)
            and str((row.get("booking_details") or {}).get("article_number") or row.get("article_number") or "")
            == order.india_post_barcode
        ),
        None,
    )
    if not record:
        raise IndiaPostFulfillmentError("India Post has no tracking record for this barcode yet.")
    events = _tracking_event_list(record)
    status_value = str(events[0].get("event") if events else "").strip()
    delivery = record.get("del_status")
    delivery = delivery.get("del_status") if isinstance(delivery, dict) else delivery
    if delivery and "not delivered" not in str(delivery).casefold():
        status_value = str(delivery).strip()
    order.india_post_tracking_status = status_value[:100]
    order.india_post_tracking_events = events
    order.india_post_tracking_last_synced_at = timezone.now()
    order.india_post_last_error = ""
    order.status = _local_status_from_india_post(record, events, order.status)
    order.save(
        update_fields=(
            "india_post_tracking_status",
            "india_post_tracking_events",
            "india_post_tracking_last_synced_at",
            "india_post_last_error",
            "status",
            "updated_at",
        )
    )
    return record


def _label_payload(order):
    if not order.india_post_barcode or order.india_post_booking_status != "Booked":
        raise IndiaPostFulfillmentError("Book the India Post article before downloading its label.")
    sender = _sender_profile()
    recipient = _recipient_profile(order)
    weight = _order_weight_grams(order)
    dimensions = _parcel_dimensions()
    office_name = order.india_post_booking_office_name
    office_pin = order.india_post_dropoff_pincode or sender["pincode"]
    service_type = "Business Parcel"
    booked_at = order.india_post_booked_at or timezone.now()
    quote = order.shipping_quote if isinstance(order.shipping_quote, dict) else {}
    return {
        "customer_id": int(
            getattr(settings, "INDIA_POST_BULK_CUSTOMER_ID", "")
            or getattr(settings, "INDIA_POST_API_USERNAME", "")
        ),
        "destination_pin": recipient["pincode"],
        "booking_datetime": booked_at.strftime("%d-%m-%Y %H:%M:%S"),
        "channel_type": "E",
        "user_type": "R",
        "user_id": int(
            getattr(settings, "INDIA_POST_BULK_CUSTOMER_ID", "")
            or getattr(settings, "INDIA_POST_API_USERNAME", "")
        ),
        "barcode_no": order.india_post_barcode,
        "service_type": service_type,
        "booking_type": "COMMERCIAL",
        "article_length": dimensions["length"],
        "article_breadth": dimensions["breadth_diameter"],
        "article_height": dimensions["height"],
        "charged_weight": weight,
        "physical_weight": weight,
        "volumetric_weight": quote.get("chargeable_weight_grams", weight),
        "insurance_flag": False,
        "insurance_value": 0,
        "recipient_name": recipient["name"],
        "recipient_mobile": recipient["mobile"],
        "recipient_addressl1": recipient["address_lines"][0],
        "recipient_addressl2": recipient["address_lines"][1],
        "recipient_addressl3": recipient["address_lines"][2],
        "recipient_city": recipient["city"],
        "recipient_pin": recipient["pincode"],
        "recipient_state": "",
        "sender_name": sender["name"],
        "sender_mobile": sender["mobile"],
        "sender_addressl1": sender["address_lines"][0],
        "sender_addressl2": sender["address_lines"][1],
        "sender_addressl3": sender["address_lines"][2],
        "sender_city": sender["city"],
        "sender_pin": sender["pincode"],
        "sender_state": sender["state"],
        "transmission_mode": str(getattr(settings, "INDIA_POST_LABEL_TRANSMISSION_MODE", "S") or "S").upper(),
        "payment_mode": "CO",
        "booking_office_name": office_name,
        "booking_office_pin": office_pin,
        "size": "A6",
        "total_amount": float(order.shipping_charge),
        "payment_status": "PC",
        "Identifier": "Domestic",
        "bkg_ref_id": order.india_post_booking_reference,
    }


def download_local_order_india_post_label(order_id):
    order = Order.objects.select_related("address", "user").get(pk=order_id)
    if order.fulfillment_provider != "india_post":
        raise IndiaPostFulfillmentError("This order is assigned to a different fulfilment provider.")
    payload = _label_payload(order)
    return IndiaPostDirectAPI.create_label(payload)


def sync_order_to_shipping_provider(order_id):
    """Dispatch paid-order fulfilment to the provider selected in settings."""

    order = Order.objects.get(pk=order_id)
    if order.fulfillment_provider == "india_post":
        if getattr(settings, "INDIA_POST_AUTO_BOOKING_ENABLED", False):
            quote = order.shipping_quote if isinstance(order.shipping_quote, dict) else {}
            if quote.get("free_delivery") or quote.get("tariff_source") != "india_post_api":
                return None
            try:
                return book_local_order_in_india_post(order_id)
            except IndiaPostFulfillmentError as error:
                Order.objects.filter(pk=order_id).update(
                    india_post_last_error=str(error)[:500],
                    updated_at=timezone.now(),
                )
                logger.warning("Automatic India Post booking was not completed for order %s", order_id)
        return None
    from .prodinent import sync_order_to_prodinent

    return sync_order_to_prodinent(order_id)
