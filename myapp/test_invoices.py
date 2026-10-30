from django.test import TestCase
from rest_framework.test import APIClient

from .models import Address, Invoice, Order, User


class InvoiceLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="invoice-customer@example.invalid",
            password="InvoicePass123!",
            role="Customer",
        )
        self.address = Address.objects.create(
            user=self.user,
            full_name="Invoice Customer",
            address_line="Main Road",
            city="Kannur",
            postal_code="670001",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_paid_order_gets_one_invoice_and_customer_orders_expose_it(self):
        order = Order.objects.create(
            user=self.user,
            address=self.address,
            total_amount="125.00",
            payment_status="Paid",
            status="Processing",
        )

        invoice = Invoice.objects.get(order=order)
        self.assertEqual(invoice.invoice_number, f"INV-{order.pk:06d}")

        order.save()
        self.assertEqual(Invoice.objects.filter(order=order).count(), 1)

        response = self.client.get("/my-orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["invoice"]["invoice_number"], invoice.invoice_number)

    def test_invoice_is_issued_when_an_existing_order_becomes_paid(self):
        order = Order.objects.create(
            user=self.user,
            address=self.address,
            total_amount="125.00",
            payment_status="Pending",
        )
        self.assertFalse(Invoice.objects.filter(order=order).exists())

        order.payment_status = "Paid"
        order.save(update_fields=("payment_status", "updated_at"))

        self.assertTrue(Invoice.objects.filter(order=order).exists())
