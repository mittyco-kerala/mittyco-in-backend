from types import SimpleNamespace
from unittest import TestCase

from .shipping import (
    IndiaPostShippingError,
    calculate_india_post_charge,
    calculate_cart_weight_grams,
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
