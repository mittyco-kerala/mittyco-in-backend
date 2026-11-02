import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import RazorpayCheckout


class RazorpayWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="webhook@example.com",
            password="test-password",
        )
        self.checkout = RazorpayCheckout.objects.create(
            user=self.user,
            razorpay_order_id="order_test_123",
            amount="120.54",
            currency="INR",
            snapshot={"products": [], "total": "120.54"},
            status="Active",
        )

    @staticmethod
    def _signed_body(payload, secret="webhook-secret"):
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return raw_body, signature

    @override_settings(
        RAZORPAY_ENABLED=True,
        RAZORPAY_WEBHOOK_SECRET="webhook-secret",
    )
    def test_rejects_invalid_webhook_signature_before_processing(self):
        payload = {
            "entity": "event",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_123",
                        "order_id": self.checkout.razorpay_order_id,
                        "amount": 12054,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_body, _ = self._signed_body(payload)

        with patch("payment.razorpay_views.fulfill_checkout") as fulfill:
            response = self.client.post(
                "/payment/razorpay-webhook/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="invalid",
            )

        self.assertEqual(response.status_code, 400)
        fulfill.assert_not_called()

    @override_settings(
        RAZORPAY_ENABLED=True,
        RAZORPAY_WEBHOOK_SECRET="webhook-secret",
    )
    def test_fulfils_a_valid_captured_payment(self):
        payload = {
            "entity": "event",
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_123",
                        "order_id": self.checkout.razorpay_order_id,
                        "amount": 12054,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_body, signature = self._signed_body(payload)

        with patch(
            "payment.razorpay_views.fulfill_checkout",
            return_value=type("Order", (), {"id": 77})(),
        ) as fulfill:
            response = self.client.post(
                "/payment/razorpay-webhook/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID="evt_test_123",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        fulfill.assert_called_once()
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, "Paid")

    @override_settings(
        RAZORPAY_ENABLED=True,
        RAZORPAY_WEBHOOK_SECRET="webhook-secret",
    )
    def test_marks_failed_payment_without_fulfilling_checkout(self):
        payload = {
            "entity": "event",
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_failed",
                        "order_id": self.checkout.razorpay_order_id,
                        "amount": 12054,
                        "currency": "INR",
                        "status": "failed",
                    }
                }
            },
        }
        raw_body, signature = self._signed_body(payload)

        with patch("payment.razorpay_views.fulfill_checkout") as fulfill:
            response = self.client.post(
                "/payment/razorpay-webhook/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
                HTTP_X_RAZORPAY_EVENT_ID="evt_test_failed",
            )

        self.assertEqual(response.status_code, 200)
        fulfill.assert_not_called()
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, "Failed")
