import hashlib
import hmac
import json
import logging
import secrets
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt

from .cashfree_views import (
    CheckoutFulfillmentError,
    _customer_name,
    _money,
    _snapshot_from_cart,
    fulfill_checkout,
)
from .models import RazorpayCheckout
from .razorpay_services import RazorpayAPIError, RazorpayService
from myapp.models import Address
from myapp.utils import PaymentRateThrottle
from myapp.customer_emails import send_pending_payment_email


logger = logging.getLogger(__name__)


def _razorpay_currency():
    currency = str(getattr(settings, "RAZORPAY_ORDER_CURRENCY", "INR") or "INR").upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("RAZORPAY_ORDER_CURRENCY must be a three-letter currency code.")
    return currency


def _amount_in_paise(amount):
    try:
        money = _money(amount)
        paise = int((money * Decimal("100")).to_integral_exact())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("The payment amount is invalid.")
    if paise <= 0:
        raise ValueError("The order total must be greater than zero.")
    return paise


def _checkout_response(checkout):
    return Response(
        {
            "key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": checkout.razorpay_order_id,
            "amount": _amount_in_paise(checkout.amount),
            "currency": checkout.currency,
            "name": "Mittyco",
            "description": "Mittyco online order",
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([PaymentRateThrottle])
def create_razorpay_order(request):
    if not getattr(settings, "RAZORPAY_ENABLED", False):
        return Response(
            {"message": "Razorpay test payments are temporarily unavailable."},
            status=status.HTTP_410_GONE,
        )

    address_id = request.data.get("address")
    if not address_id:
        return Response({"message": "Address is required"}, status=status.HTTP_400_BAD_REQUEST)

    address = Address.objects.filter(id=address_id, user=request.user).first()
    if not address:
        return Response({"message": "Address not found"}, status=status.HTTP_404_NOT_FOUND)

    idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY", "").strip()[:255] or None
    if idempotency_key:
        previous = RazorpayCheckout.objects.filter(
            user=request.user,
            idempotency_key=idempotency_key,
        ).first()
        if previous:
            return _checkout_response(previous)

    try:
        currency = _razorpay_currency()
        snapshot = _snapshot_from_cart(request.user, address=address)
        amount = _money(snapshot["total"])
        amount_in_paise = _amount_in_paise(amount)
    except ValueError as error:
        return Response({"message": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        razorpay_order = RazorpayService.create_order(
            amount=amount_in_paise,
            currency=currency,
            receipt=f"mittyco-{request.user.id}-{secrets.token_hex(8)}",
            notes={
                "user_id": str(request.user.id),
                "address_id": str(address.id),
            },
        )
        razorpay_order_id = str(razorpay_order.get("id") or "").strip()
        provider_amount = int(razorpay_order.get("amount") or 0)
        provider_currency = str(razorpay_order.get("currency") or "").upper()
        if (
            not razorpay_order_id
            or provider_amount != amount_in_paise
            or provider_currency != currency
        ):
            raise RazorpayAPIError("Razorpay returned an invalid order.")
    except RazorpayAPIError as error:
        logger.exception(
            "Razorpay order creation failed",
            extra={"user_id": request.user.id, "razorpay_status": error.status_code},
        )
        return Response(
            {"message": "Unable to start Razorpay payment. Please try again later."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    checkout = RazorpayCheckout.objects.create(
        user=request.user,
        address=address,
        razorpay_order_id=razorpay_order_id,
        idempotency_key=idempotency_key,
        amount=amount,
        currency=currency,
        snapshot=snapshot,
        status="Active",
    )
    # This is a checkout-started notification, not proof of payment. The
    # invoice email is sent later from the paid-order fulfilment hook.
    send_pending_payment_email(checkout, provider="Razorpay")
    response = _checkout_response(checkout)
    response.data.update(
        {
            "prefill": {
                "name": _customer_name(request.user, address),
                "email": request.user.email,
                "contact": str(address.phone or ""),
            },
            "theme": {"color": "#1e654d"},
        }
    )
    return response


def _signature_is_valid(order_id, payment_id, signature):
    secret = str(getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, str(signature))


def _razorpay_webhook_signature_is_valid(raw_body, signature):
    secret = str(getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "") or "").strip()
    signature = str(signature or "").strip()
    if not secret or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _razorpay_webhook_entities(event):
    payload = event.get("payload") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    order = (payload.get("order") or {}).get("entity") or {}
    if not isinstance(payment, dict):
        payment = {}
    if not isinstance(order, dict):
        order = {}
    return payment, order


def _razorpay_webhook_order_id(payment, order):
    return str(payment.get("order_id") or order.get("id") or "").strip()


def _razorpay_webhook_amount_and_currency(event_name, payment, order):
    if event_name == "payment.captured":
        return payment.get("amount"), payment.get("currency")
    return order.get("amount_paid") or order.get("amount"), order.get("currency")


def _razorpay_webhook_payment_is_valid(checkout, event_name, payment, order):
    amount, currency = _razorpay_webhook_amount_and_currency(event_name, payment, order)
    try:
        provider_amount = int(amount or 0)
        expected_amount = _amount_in_paise(checkout.amount)
    except (TypeError, ValueError, InvalidOperation):
        return False

    if provider_amount != expected_amount:
        return False
    if str(currency or "").upper() != checkout.currency.upper():
        return False

    provider_status = str(
        payment.get("status") if event_name == "payment.captured" else order.get("status")
    ).lower()
    if event_name == "payment.captured" and provider_status != "captured":
        return False
    if event_name == "order.paid" and provider_status and provider_status != "paid":
        return False
    return True


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([PaymentRateThrottle])
def verify_razorpay_payment(request):
    if not getattr(settings, "RAZORPAY_ENABLED", False):
        return Response(
            {"message": "Razorpay test payments are temporarily unavailable."},
            status=status.HTTP_410_GONE,
        )

    razorpay_order_id = str(request.data.get("razorpay_order_id") or "").strip()
    payment_id = str(request.data.get("razorpay_payment_id") or "").strip()
    signature = str(request.data.get("razorpay_signature") or "").strip()
    checkout = RazorpayCheckout.objects.filter(
        razorpay_order_id=razorpay_order_id,
        user=request.user,
    ).first()
    if not checkout:
        return Response({"message": "Payment order not found."}, status=status.HTTP_404_NOT_FOUND)
    if checkout.order_id:
        return Response(
            {
                "message": "Payment successful",
                "order_id": checkout.order_id,
                "razorpay_order_id": checkout.razorpay_order_id,
            }
        )
    if not payment_id or not _signature_is_valid(razorpay_order_id, payment_id, signature):
        return Response({"message": "Payment signature verification failed."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        payment = RazorpayService.fetch_payment(payment_id)
        provider_order_id = str(payment.get("order_id") or "").strip()
        provider_amount = int(payment.get("amount") or 0)
        provider_currency = str(payment.get("currency") or "").upper()
        provider_status = str(payment.get("status") or "").lower()
        if (
            provider_order_id != checkout.razorpay_order_id
            or provider_amount != _amount_in_paise(checkout.amount)
            or provider_currency != checkout.currency
        ):
            raise CheckoutFulfillmentError("Payment details do not match the checkout amount.")
        if provider_status != "captured":
            return Response(
                {"message": "Payment is not captured yet.", "payment_status": provider_status},
                status=status.HTTP_409_CONFLICT,
            )
    except (RazorpayAPIError, CheckoutFulfillmentError, ValueError) as error:
        logger.exception(
            "Razorpay payment verification failed",
            extra={"razorpay_order_id": razorpay_order_id, "payment_id": payment_id},
        )
        return Response({"message": str(error) or "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)

    checkout.status = "Paid"
    checkout.save(update_fields=("status", "updated_at"))
    try:
        order = fulfill_checkout(
            checkout,
            checkout_model=RazorpayCheckout,
            payment_method="Razorpay",
        )
    except CheckoutFulfillmentError as error:
        checkout.status = "Fulfillment Error"
        checkout.save(update_fields=("status", "updated_at"))
        logger.exception("Razorpay payment succeeded but order fulfilment failed")
        return Response(
            {"message": str(error), "payment_status": "Paid"},
            status=status.HTTP_409_CONFLICT,
        )
    return Response(
        {
            "message": "Payment successful",
            "order_id": order.id,
            "razorpay_order_id": checkout.razorpay_order_id,
        }
    )


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def razorpay_webhook(request):
    """Accept signed Razorpay payment events and fulfil a checkout once.

    The raw request bytes are verified before JSON parsing. Razorpay may send
    both ``payment.captured`` and ``order.paid`` for one checkout, so the
    shared fulfilment function's row lock and existing order relation provide
    the idempotency guard.
    """
    if not getattr(settings, "RAZORPAY_ENABLED", False):
        return Response(
            {"message": "Razorpay payments are disabled."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    raw_body = request.body
    if len(raw_body) > 1_000_000:
        return HttpResponse(status=413)

    signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE", "")
    if not _razorpay_webhook_signature_is_valid(raw_body, signature):
        return Response(
            {"message": "Invalid webhook signature."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response(
            {"message": "Invalid webhook payload."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(event, dict):
        return Response(
            {"message": "Invalid webhook payload."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    event_name = str(event.get("event") or "").strip()
    if event_name not in {"payment.captured", "order.paid", "payment.failed"}:
        return Response({"status": "ignored"})

    payment, order = _razorpay_webhook_entities(event)
    razorpay_order_id = _razorpay_webhook_order_id(payment, order)
    if not razorpay_order_id:
        logger.warning("Razorpay webhook did not contain an order ID")
        return Response({"status": "ignored"})

    checkout = RazorpayCheckout.objects.filter(
        razorpay_order_id=razorpay_order_id,
    ).first()
    if not checkout:
        logger.warning(
            "Received Razorpay webhook for unknown order",
            extra={"razorpay_order_id": razorpay_order_id},
        )
        return Response({"status": "ignored"})

    if event_name == "payment.failed":
        if not checkout.order_id and checkout.status not in {"Paid", "Fulfilled"}:
            checkout.status = "Failed"
            checkout.save(update_fields=("status", "updated_at"))
        return Response({"status": "ok"})

    if not _razorpay_webhook_payment_is_valid(checkout, event_name, payment, order):
        logger.warning(
            "Razorpay webhook payment did not match checkout",
            extra={"razorpay_order_id": razorpay_order_id, "event": event_name},
        )
        return Response(
            {"message": "Webhook payment does not match the checkout."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if checkout.order_id:
        return Response({"status": "ok"})

    checkout.status = "Paid"
    checkout.save(update_fields=("status", "updated_at"))
    try:
        fulfill_checkout(
            checkout,
            checkout_model=RazorpayCheckout,
            payment_method="Razorpay",
        )
    except CheckoutFulfillmentError:
        checkout.status = "Fulfillment Error"
        checkout.save(update_fields=("status", "updated_at"))
        logger.exception(
            "Razorpay webhook payment succeeded but order fulfilment failed",
            extra={"razorpay_order_id": razorpay_order_id},
        )
        return Response(
            {"message": "Payment received but order fulfilment failed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception:
        logger.exception(
            "Unexpected Razorpay webhook fulfilment failure",
            extra={"razorpay_order_id": razorpay_order_id},
        )
        return Response(
            {"message": "Payment received but order processing failed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def razorpay_payment_success(request):
    order_id = str(request.GET.get("order_id") or "").strip()
    checkout = RazorpayCheckout.objects.filter(
        razorpay_order_id=order_id,
        user=request.user,
    ).select_related("order").first()
    if not checkout:
        return Response({"message": "Payment order not found."}, status=status.HTTP_404_NOT_FOUND)
    if not checkout.order_id:
        return Response(
            {"message": "Payment has not been verified yet.", "payment_status": checkout.status},
            status=status.HTTP_409_CONFLICT,
        )
    return Response({"message": "Payment successful", "order_id": checkout.order_id})
