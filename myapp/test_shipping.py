from types import SimpleNamespace
from unittest.mock import patch
from unittest import TestCase

from django.test import override_settings

from .shipping import (
    IndiaPostShippingError,
    calculate_india_post_charge,
    calculate_cart_weight_grams,
    calculate_cart_shipping,
    calculate_distance_km,
    is_within_free_delivery_radius,
    parse_weight_grams,
)


class IndiaPostShippingTests(TestCase):
    def test_local_parcel_uses_official_retail_rate(self):
        quote = calculate_india_post_charge(
            weight_grams=500,
            origin_pincode="682001",
            destination_pincode="682001",
        )

        self.assertEqual(quote["shipping_class"], "LOCAL")
        self.assertEqual(quote["amount"], "28.00")

    def test_same_state_parcel_uses_within_state_rate(self):
        quote = calculate_india_post_charge(
            weight_grams=750,
            origin_pincode="682001",
            destination_pincode="682018",
            origin_state="Kerala",
            destination_state="Kerala",
        )

        self.assertEqual(quote["shipping_class"], "WITHIN_STATE")
        self.assertEqual(quote["amount"], "91.00")

    def test_other_state_rate_adds_each_extra_kg(self):
        quote = calculate_india_post_charge(
            weight_grams=6500,
            origin_pincode="682001",
            destination_pincode="560001",
        )

        self.assertEqual(quote["shipping_class"], "OTHER_STATE")
        self.assertEqual(quote["amount"], "695.00")

    def test_invalid_pincode_or_weight_is_rejected(self):
        with self.assertRaises(IndiaPostShippingError):
            calculate_india_post_charge(
                weight_grams=0,
                origin_pincode="682001",
                destination_pincode="560001",
            )
        with self.assertRaises(IndiaPostShippingError):
            calculate_india_post_charge(
                weight_grams=500,
                origin_pincode="6820",
                destination_pincode="560001",
            )

    def test_weight_parser_supports_grams_and_kilograms(self):
        self.assertEqual(parse_weight_grams("250 g"), 250)
        self.assertEqual(parse_weight_grams("1 KG"), 1000)
        self.assertIsNone(parse_weight_grams("1 litre"))

    def test_cart_weight_uses_explicit_weight_then_unit_name_then_default(self):
        first = SimpleNamespace(
            quantity=2,
            variant=SimpleNamespace(shipping_weight_grams=400),
            variant_unit=None,
        )
        second = SimpleNamespace(
            quantity=1,
            variant=SimpleNamespace(shipping_weight_grams=None),
            variant_unit=SimpleNamespace(
                shipping_weight_grams=None,
                unit=SimpleNamespace(name="1 KG"),
            ),
        )
        third = SimpleNamespace(
            quantity=1,
            variant=SimpleNamespace(shipping_weight_grams=None),
            variant_unit=SimpleNamespace(
                shipping_weight_grams=None,
                unit=SimpleNamespace(name="1 litre"),
            ),
        )

        self.assertEqual(calculate_cart_weight_grams([first, second, third]), 2300)

    def test_free_delivery_uses_latitude_and_longitude_with_five_km_boundary(self):
        self.assertEqual(
            calculate_distance_km(12.000000, 75.000000, 12.000000, 75.000000),
            0.0,
        )
        self.assertTrue(
            is_within_free_delivery_radius(
                origin_latitude=12.000000,
                origin_longitude=75.000000,
                destination_latitude=12.040000,
                destination_longitude=75.000000,
                radius_km=5,
            )
        )
        self.assertFalse(
            is_within_free_delivery_radius(
                origin_latitude=12.000000,
                origin_longitude=75.000000,
                destination_latitude=12.060000,
                destination_longitude=75.000000,
                radius_km=5,
            )
        )

    @override_settings(
        INDIA_POST_ORIGIN_PINCODE="670353",
        INDIA_POST_ORIGIN_STATE="Kerala",
        INDIA_POST_ORIGIN_LATITUDE="12.000000",
        INDIA_POST_ORIGIN_LONGITUDE="75.000000",
        INDIA_POST_FREE_DELIVERY_RADIUS_KM="5",
    )
    def test_cart_shipping_is_free_when_delivery_location_is_within_five_km(self):
        cart_item = SimpleNamespace(
            quantity=1,
            variant=SimpleNamespace(shipping_weight_grams=500),
            variant_unit=None,
        )
        address = SimpleNamespace(
            postal_code="670353",
            latitude="12.040000",
            longitude="75.000000",
        )

        quote = calculate_cart_shipping([cart_item], address)

        self.assertEqual(quote["amount"], "0.00")
        self.assertTrue(quote["free_delivery"])
        self.assertEqual(quote["shipping_class"], "FREE_LOCAL")

    @override_settings(
        INDIA_POST_ORIGIN_PINCODE="670353",
        INDIA_POST_ORIGIN_STATE="Kerala",
        INDIA_POST_ORIGIN_LATITUDE="12.000000",
        INDIA_POST_ORIGIN_LONGITUDE="75.000000",
        INDIA_POST_FREE_DELIVERY_RADIUS_KM="5",
    )
    @patch("myapp.shipping.lookup_pincode_state", return_value="Kerala")
    def test_cart_shipping_uses_india_post_when_delivery_location_is_outside_radius(self, _lookup):
        cart_item = SimpleNamespace(
            quantity=1,
            variant=SimpleNamespace(shipping_weight_grams=500),
            variant_unit=None,
        )
        address = SimpleNamespace(
            postal_code="670307",
            latitude="12.060000",
            longitude="75.000000",
        )

        quote = calculate_cart_shipping([cart_item], address)

        self.assertEqual(quote["amount"], "65.00")
        self.assertFalse(quote["free_delivery"])
        self.assertEqual(quote["shipping_class"], "WITHIN_STATE")
