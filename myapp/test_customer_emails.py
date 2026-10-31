from decimal import Decimal

from django.test import SimpleTestCase

from .customer_emails import (
    build_invoice_email,
    build_pending_payment_email,
    build_welcome_email,
)


class CustomerEmailContentTests(SimpleTestCase):
    def test_welcome_email_lists_bonus_without_private_assignment_code(self):
        content = build_welcome_email(
            first_name="Asha",
            bonuses=[
                {
                    "name": "Welcome 10%",
                    "discount_text": "10% off",
                    "end_date": "31 Dec 2026",
                }
            ],
            site_url="https://mittyco.example",
        )

        self.assertEqual(content["subject"], "Welcome to Mittyco")
        self.assertIn("Welcome 10%", content["text"])
        self.assertIn("10% off", content["text"])
        self.assertNotIn("WB-SECRET", content["text"])
        self.assertIn("https://mittyco.example", content["html"])

    def test_pending_payment_email_contains_provider_reference_and_items(self):
        content = build_pending_payment_email(
            customer_name="Asha",
            provider="Razorpay",
            reference="order_test_123",
            amount=Decimal("135.54"),
            items=[{"name": "Mango Pickles", "quantity": 2, "total": Decimal("120.54")}],
            site_url="https://mittyco.example",
        )

        self.assertIn("payment is pending", content["text"].lower())
        self.assertIn("order_test_123", content["text"])
        self.assertIn("Mango Pickles", content["text"])
        self.assertIn("135.54", content["text"])

    def test_invoice_email_contains_invoice_number_and_paid_order_summary(self):
        content = build_invoice_email(
            customer_name="Asha",
            order_number="ORD-000042",
            invoice_number="INV-000042",
            issued_at="31 Oct 2026, 10:30 AM",
            payment_method="Razorpay",
            total=Decimal("135.54"),
            items=[{"name": "Mango Pickles", "quantity": 1, "total": Decimal("120.54")}],
            site_url="https://mittyco.example",
        )

        self.assertEqual(content["subject"], "Invoice INV-000042 from Mittyco")
        self.assertIn("INV-000042", content["text"])
        self.assertIn("Payment status: Paid", content["text"])
        self.assertIn("Mango Pickles", content["html"])
        self.assertIn("135.54", content["html"])
