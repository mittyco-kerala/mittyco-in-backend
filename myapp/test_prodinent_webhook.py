import hashlib
import hmac
import json
from contextlib import nullcontext
from unittest.mock import Mock, patch

from django.test import Client, SimpleTestCase, override_settings


class ProdinentWebhookTests(SimpleTestCase):
    @override_settings(PRODINENT_WEBHOOK_SECRET="webhook-secret")
    def test_rejects_webhook_without_valid_signature(self):
        response = Client().post(
            "/prodinent/webhook/",
            data=json.dumps({"externalOrderId": "ORD-000001", "status": "Manifested"}),
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE="invalid",
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(PRODINENT_WEBHOOK_SECRET="webhook-secret")
    @patch("myapp.prodinent_webhook._find_order", return_value=None)
    def test_accepts_provider_token_when_signature_header_is_unavailable(self, _find_order):
        response = Client().post(
            "/prodinent/webhook/?token=webhook-secret",
            data=json.dumps({"externalOrderId": "ORD-000001", "status": "Manifested"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True, "matched": False})

    @override_settings(PRODINENT_WEBHOOK_SECRET="webhook-secret")
    @patch("myapp.prodinent_webhook._find_order", return_value=None)
    def test_accepts_provider_token_with_provider_suffix(self, _find_order):
        response = Client().post(
            "/prodinent/webhook/?token=webhook-secret123456789",
            data=json.dumps({"externalOrderId": "ORD-000001", "status": "Manifested"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True, "matched": False})

    @override_settings(PRODINENT_WEBHOOK_SECRET="webhook-secret")
    @patch("myapp.prodinent_webhook.transaction.atomic", return_value=nullcontext())
    @patch("myapp.prodinent_webhook.apply_tracking_response")
    @patch("myapp.prodinent_webhook._find_order")
    def test_valid_webhook_updates_matching_order_status(self, find_order, apply_tracking, _atomic):
        order = Mock(status="Processing")
        order.refresh_from_db = Mock()
        order.save = Mock()
        find_order.return_value = order
        apply_tracking.return_value = {"status": "Manifested"}
        payload = {"externalOrderId": "ORD-000001", "status": "Manifested"}
        raw_body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            b"webhook-secret", raw_body, hashlib.sha256
        ).hexdigest()

        response = Client().post(
            "/prodinent/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True, "matched": True})
        self.assertEqual(order.status, "Shipped")
