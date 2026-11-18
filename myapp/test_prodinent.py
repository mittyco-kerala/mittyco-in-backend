from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .prodinent import (
    ProdinentAPIError,
    ProdinentService,
    build_order_payload,
)


class ProdinentServiceTests(SimpleTestCase):
    @override_settings(
        PRODINENT_ENABLED=True,
        PRODINENT_BASE_URL="https://api.prodinent.com/api/v1",
        PRODINENT_CONNECTION_KEY="pb_live_test-key",
        PRODINENT_LIVE_WRITES_ENABLED=False,
    )
    @patch("myapp.prodinent.requests.request")
    def test_check_connection_uses_bearer_auth_without_logging_the_key(self, request):
        response = Mock(ok=True, status_code=200, text="")
        response.json.return_value = {"success": True, "connectionId": "pcon_test"}
        request.return_value = response

        result = ProdinentService.check_connection()

        self.assertEqual(result["connectionId"], "pcon_test")
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer pb_live_test-key")
        self.assertNotIn("pb_live_test-key", str(kwargs.get("json")))

    @override_settings(
        PRODINENT_ENABLED=True,
        PRODINENT_BASE_URL="https://api.prodinent.com/api/v1",
        PRODINENT_CONNECTION_KEY="pb_live_test-key",
        PRODINENT_LIVE_WRITES_ENABLED=False,
    )
    @patch("myapp.prodinent.requests.request")
    def test_create_order_is_blocked_until_live_writes_are_enabled(self, request):
        with self.assertRaisesMessage(
            ProdinentAPIError,
            "Prodinent live writes are disabled.",
        ):
            ProdinentService.create_order({"externalOrderId": "ORD-000001"})

        request.assert_not_called()

    @override_settings(
        PRODINENT_ENABLED=True,
        PRODINENT_BASE_URL="https://api.prodinent.com/api/v1",
        PRODINENT_CONNECTION_KEY="pb_live_test-key",
        PRODINENT_LIVE_WRITES_ENABLED=True,
    )
    @patch("myapp.prodinent.requests.request")
    def test_create_order_returns_provider_payload_when_live_writes_are_enabled(self, request):
        response = Mock(ok=True, status_code=200, text="")
        response.json.return_value = {
            "success": True,
            "duplicate": False,
            "order": {"orderID": "424578", "status": "Pending"},
        }
        request.return_value = response

        result = ProdinentService.create_order(
            {"externalOrderId": "ORD-000001"}
        )

        self.assertEqual(result["order"]["orderID"], "424578")
        self.assertEqual(request.call_args.args[:2], ("POST", "https://api.prodinent.com/api/v1/orders"))

    @override_settings(
        PRODINENT_ENABLED=True,
        PRODINENT_BASE_URL="https://api.prodinent.com/api/v1",
        PRODINENT_CONNECTION_KEY="pb_live_test-key",
        PRODINENT_LIVE_WRITES_ENABLED=True,
    )
    @patch("myapp.prodinent.requests.request")
    def test_assign_barcode_uses_default_series(self, request):
        response = Mock(ok=True, status_code=200, text="")
        response.json.return_value = {
            "success": True,
            "order": {"orderID": "424578", "articleId": "EA123456789IN", "status": "Pending"},
        }
        request.return_value = response

        result = ProdinentService.assign_barcode("ORD-000042")

        self.assertEqual(result["order"]["articleId"], "EA123456789IN")
        self.assertEqual(
            request.call_args.args[:2],
            ("POST", "https://api.prodinent.com/api/v1/orders/ORD-000042/barcode"),
        )
        self.assertEqual(request.call_args.kwargs["json"], {"assignFromSeries": True})

    @override_settings(
        PRODINENT_ENABLED=True,
        PRODINENT_BASE_URL="https://api.prodinent.com/api/v1",
        PRODINENT_CONNECTION_KEY="pb_live_test-key",
        PRODINENT_LIVE_WRITES_ENABLED=False,
    )
    @patch("myapp.prodinent.requests.request")
    def test_label_download_returns_pdf_without_json_parsing(self, request):
        response = Mock(ok=True, status_code=200, headers={"Content-Type": "application/pdf"})
        response.content = b"%PDF-test"
        request.return_value = response

        result = ProdinentService.download_label("ORD-000042")

        self.assertEqual(result, b"%PDF-test")
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "https://api.prodinent.com/api/v1/orders/ORD-000042/label"),
        )

    def test_build_order_payload_can_request_barcode_and_booking(self):
        with override_settings(
            INDIA_POST_DEFAULT_ITEM_WEIGHT_GRAMS=500,
            PRODINENT_WAREHOUSE_ID="warehouse-test",
            PRODINENT_AUTO_ASSIGN_BARCODE=True,
            PRODINENT_AUTO_BOOK_SHIPMENT=True,
        ), patch("myapp.prodinent.lookup_pincode_state", return_value="Kerala"):
            item = SimpleNamespace(
                variant_unit=SimpleNamespace(
                    sku="PICKLE-500",
                    shipping_weight_grams=450,
                    variant=SimpleNamespace(sku=None, shipping_weight_grams=None),
                ),
                product=SimpleNamespace(name="Mango Pickle"),
                quantity=1,
                price=Decimal("120.50"),
            )
            order = SimpleNamespace(
                id=42,
                payment_method="Razorpay",
                shipping_charge=Decimal("28.00"),
                user=SimpleNamespace(email="customer@example.com"),
                address=SimpleNamespace(
                    full_name="Asha Customer",
                    phone="9876543210",
                    address_line="12 Sample Street",
                    postal_code="670001",
                    city="Kannur",
                    country="India",
                ),
                items=[item],
            )

            payload = build_order_payload(order)

        self.assertTrue(payload["assignFromSeries"])
        self.assertTrue(payload["book"])

    def test_tracking_response_updates_provider_fields_and_local_status_mapping(self):
        order = Mock(
            prodinent_status="Pending",
            prodinent_article_id=None,
            prodinent_tracking_link=None,
            prodinent_label_available=False,
            prodinent_last_error="old error",
            status="Processing",
        )
        order.save = Mock()
        with patch("myapp.prodinent.timezone.now", return_value="now"):
            from .prodinent import apply_tracking_response, local_order_status_for_prodinent

            apply_tracking_response(
                order,
                {
                    "success": True,
                    "tracking": {
                        "status": "Manifested",
                        "articleId": "EA123456789IN",
                        "trackingLink": "https://example.test/track/EA123456789IN",
                        "labelAvailable": True,
                    },
                },
            )

        self.assertEqual(order.prodinent_article_id, "EA123456789IN")
        self.assertTrue(order.prodinent_label_available)
        self.assertEqual(local_order_status_for_prodinent("Manifested", "Processing"), "Shipped")
        self.assertEqual(local_order_status_for_prodinent("Out for delivery", "Shipped"), "Shipped")

    @override_settings(
        INDIA_POST_DEFAULT_ITEM_WEIGHT_GRAMS=500,
        PRODINENT_WAREHOUSE_ID="warehouse-test",
    )
    @patch("myapp.prodinent.lookup_pincode_state", return_value="Kerala")
    def test_build_order_payload_maps_local_order_to_prodinent_contract(self, _lookup):
        variant = SimpleNamespace(sku="PICKLE-500", shipping_weight_grams=450)
        unit = SimpleNamespace(sku=None, shipping_weight_grams=None, variant=variant)
        item = SimpleNamespace(
            variant_unit=unit,
            product=SimpleNamespace(name="Mango Pickle"),
            quantity=2,
            price=Decimal("120.50"),
        )
        order = SimpleNamespace(
            id=42,
            payment_method="Razorpay",
            shipping_charge=Decimal("28.00"),
            user=SimpleNamespace(email="customer@example.com"),
            address=SimpleNamespace(
                full_name="Asha Customer",
                phone="9876543210",
                address_line="12 Sample Street",
                postal_code="670001",
                city="Kannur",
                country="India",
            ),
            items=[item],
        )

        payload = build_order_payload(order)

        self.assertEqual(payload["externalOrderId"], "ORD-000042")
        self.assertEqual(payload["warehouseId"], "warehouse-test")
        self.assertEqual(payload["payment"], {"method": "Pre-paid"})
        self.assertEqual(payload["shippingAddress"]["state"], "Kerala")
        self.assertEqual(payload["products"][0]["sku"], "PICKLE-500")
        self.assertEqual(payload["products"][0]["qty"], 2)
        self.assertEqual(payload["deliveryCharge"], 28.0)
        self.assertEqual(payload["shipment"], {"weightGrams": 900})


