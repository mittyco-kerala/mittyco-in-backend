from django.test import SimpleTestCase

from .india_post_settings_api import IndiaPostSettingsSerializer, _settings_error


class IndiaPostSettingsSerializerTests(SimpleTestCase):
    def test_current_prodinent_route_can_be_kept_while_staging_settings(self):
        serializer = IndiaPostSettingsSerializer(data={"fulfillment_provider": "prodinent"}, partial=True)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_direct_route_waits_for_booking_and_weight_readiness(self):
        readiness = {
            "tariff_ready": True,
            "five_km_delivery_ready": True,
            "booking_ready": True,
            "product_weights_ready": False,
            "products_missing_shipping_weights": 31,
            "auto_booking_ready": False,
        }
        updated = {
            "fulfillment_provider": "india_post",
            "direct_tariff_enabled": True,
            "fulfillment_enabled": True,
            "live_booking_enabled": True,
        }

        error = _settings_error("prodinent", updated, readiness)

        self.assertIn("31", error["fulfillment_provider"])

    def test_direct_routing_cannot_be_switched_back_to_prodinent(self):
        error = _settings_error(
            "india_post",
            {"fulfillment_provider": "prodinent"},
            {},
        )

        self.assertIn("cannot be re-enabled", error["fulfillment_provider"])

    def test_free_delivery_radius_cannot_exceed_five_kilometres(self):
        serializer = IndiaPostSettingsSerializer(data={"free_delivery_radius_km": "5.01"}, partial=True)

        self.assertFalse(serializer.is_valid())

    def test_store_coordinates_must_be_entered_as_a_pair(self):
        serializer = IndiaPostSettingsSerializer(data={"origin_latitude": "12.3"}, partial=True)

        self.assertFalse(serializer.is_valid())

    def test_api_secrets_are_not_part_of_dashboard_write_fields(self):
        serializer = IndiaPostSettingsSerializer()

        self.assertNotIn("api_password", serializer.fields)
        self.assertNotIn("api_username", serializer.fields)
