from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.core.cache import cache

from .shipping_integration_config import get_shipping_setting


class ShippingIntegrationConfigTests(SimpleTestCase):
    def setUp(self):
        cache.delete("myapp:shipping-integration-config:v1")

    @override_settings(SHIPPING_FULFILLMENT_PROVIDER="prodinent")
    @patch("myapp.shipping_integration_config.ShippingIntegrationConfig.objects.filter")
    def test_environment_is_used_before_dashboard_settings_are_saved(self, filter_config):
        filter_config.return_value.values_list.return_value.first.return_value = None

        self.assertEqual(
            get_shipping_setting("SHIPPING_FULFILLMENT_PROVIDER"),
            "prodinent",
        )

    @patch("myapp.shipping_integration_config.ShippingIntegrationConfig.objects.filter")
    def test_dashboard_value_overrides_environment(self, filter_config):
        filter_config.return_value.values_list.return_value.first.return_value = {
            "SHIPPING_FULFILLMENT_PROVIDER": "india_post",
            "INDIA_POST_FREE_DELIVERY_RADIUS_KM": 5,
        }

        self.assertEqual(
            get_shipping_setting("SHIPPING_FULFILLMENT_PROVIDER"),
            "india_post",
        )
        self.assertEqual(
            get_shipping_setting("INDIA_POST_FREE_DELIVERY_RADIUS_KM"),
            5,
        )

    @patch("myapp.shipping_integration_config.ShippingIntegrationConfig.objects.filter")
    def test_unknown_keys_never_read_dashboard_json(self, filter_config):
        filter_config.return_value.values_list.return_value.first.return_value = {
            "INDIA_POST_API_PASSWORD": "must-not-be-configurable-here",
        }

        self.assertEqual(get_shipping_setting("INDIA_POST_API_PASSWORD"), "")
        filter_config.assert_not_called()

