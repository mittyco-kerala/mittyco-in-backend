from unittest.mock import patch

from django.test import SimpleTestCase

from .india_post_tariff import IndiaPostTariffClient


class IndiaPostTariffClientTests(SimpleTestCase):
    @patch.object(IndiaPostTariffClient, "_access_token", return_value="test-token")
    @patch.object(IndiaPostTariffClient, "_request_json")
    def test_parses_business_parcel_production_response(self, request_json, _token):
        request_json.return_value = {
            "success": True,
            "product_code": "BUSINESS_PARCEL",
            "article_type": "Business Parcel",
            "weight": 1500,
            "chargeable_weight": 1800,
            "base_tariff": 80,
            "cgst": 7,
            "sgst": 7,
            "total_tax": 14,
            "final_amount": 94,
            "currency": "INR",
        }

        quote = IndiaPostTariffClient.calculate_quote(
            service="business_parcel",
            weight_grams=1500,
            source_pincode="670353",
            destination_pincode="670306",
            length_cm=30,
            width_cm=20,
            height_cm=15,
        )

        self.assertEqual(quote["amount"], "94.00")
        self.assertEqual(quote["base_amount"], "80.00")
        self.assertEqual(quote["tax_amount"], "14.00")
        self.assertEqual(quote["chargeable_weight_grams"], 1800)
        self.assertEqual(quote["tariff_source"], "india_post_api")

