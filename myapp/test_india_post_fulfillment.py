from unittest.mock import patch

from django.test import SimpleTestCase

from .india_post_fulfillment import IndiaPostDirectAPI


class IndiaPostDirectAPITests(SimpleTestCase):
    @patch.object(IndiaPostDirectAPI, "_request_json")
    def test_search_post_offices_unwraps_production_data_envelope(self, request_json):
        request_json.return_value = {
            "status_code": 200,
            "success": True,
            "message": "list retrieved successfully",
            "returned_records_count": 3,
            "data": [
                {
                    "pincode": 670353,
                    "office_name": "CRPF Camp Aravanchal SO",
                    "office_id": "22661066",
                    "office_type_code": "SPO",
                    "state_name": "Kerala",
                    "delivery_office_flag": True,
                    "city_name": "KANNUR",
                },
                {
                    "pincode": 670353,
                    "office_name": "Nhekly BO",
                    "office_id": "22102324",
                    "office_type_code": "BPO",
                    "state_name": "Kerala",
                    "delivery_office_flag": True,
                    "city_name": "KANNUR",
                },
                {
                    "pincode": 670353,
                    "office_name": "Non-delivery office",
                    "office_id": "22102325",
                    "office_type_code": "SO",
                    "state_name": "Kerala",
                    "delivery_office_flag": False,
                    "city_name": "KANNUR",
                },
            ],
        }

        offices = IndiaPostDirectAPI.search_post_offices("670353")

        self.assertEqual(
            offices,
            [
                {
                    "office_id": "22661066",
                    "office_name": "CRPF Camp Aravanchal SO",
                    "office_type_code": "SPO",
                    "pincode": "670353",
                    "state_name": "Kerala",
                    "city_name": "KANNUR",
                }
            ],
        )

    @patch.object(IndiaPostDirectAPI, "_request_json")
    def test_search_post_offices_still_accepts_a_bare_list(self, request_json):
        request_json.return_value = [
            {
                "pincode": "670306",
                "office_name": "Payyanur SO",
                "office_id": "22611000",
                "office_type_code": "SO",
                "state_name": "Kerala",
                "delivery_office_flag": True,
                "city_name": "Payyanur",
            }
        ]

        offices = IndiaPostDirectAPI.search_post_offices("670306")

        self.assertEqual(len(offices), 1)
        self.assertEqual(offices[0]["office_id"], "22611000")
