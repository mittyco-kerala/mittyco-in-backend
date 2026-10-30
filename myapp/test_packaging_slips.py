from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import (
    Address,
    Category,
    Order,
    OrderItem,
    PackagingSlip,
    Product,
    ProductVariant,
    SubCategory,
    User,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class PackagingSlipApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="packaging-admin@example.invalid",
            password="PackagingAdminPass123!",
        )
        self.customer = User.objects.create_user(
            email="packaging-customer@example.invalid",
            password="PackagingCustomerPass123!",
        )
        category = Category.objects.create(
            name="Packaging category",
            image="packaging-category.jpg",
        )
        subcategory = SubCategory.objects.create(
            category=category,
            name="Packaging subcategory",
        )
        self.product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Packaging product",
            description="Product used by packaging-slip tests.",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            price_type="single",
            price=Decimal("25.00"),
            stock=10,
            sku="PACKAGING-TEST-SKU",
        )
        address = Address.objects.create(
            user=self.customer,
            full_name="Packaging Customer",
            phone="9876543210",
            address_line="1 Packaging Street",
            city="Kochi",
            postal_code="682001",
            country="India",
        )
        self.orders = []
        for quantity in (1, 2):
            order = Order.objects.create(
                user=self.customer,
                address=address,
                subtotal=Decimal("25.00") * quantity,
                total_amount=Decimal("25.00") * quantity,
                payment_status="Paid",
                payment_method="RAZORPAY",
            )
            OrderItem.objects.create(
                order=order,
                product=self.product,
                quantity=quantity,
                original_price=Decimal("25.00"),
                price=Decimal("25.00"),
                total_price=Decimal("25.00") * quantity,
            )
            self.orders.append(order)

    def test_admin_can_create_one_idempotent_slip_for_multiple_orders(self):
        self.client.force_authenticate(user=self.admin)

        first = self.client.post(
            "/admin/packaging-slips/",
            {"order_ids": [self.orders[1].id, self.orders[0].id]},
            format="json",
        )

        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data["slip_number"].startswith("PKG-"))
        self.assertEqual(len(first.data["orders"]), 2)
        self.assertEqual(len(first.data["items"]), 2)
        self.assertEqual(
            len({item["barcode"] for item in first.data["items"]}),
            2,
        )

        retry = self.client.post(
            "/admin/packaging-slips/",
            {"order_ids": [self.orders[0].id, self.orders[1].id]},
            format="json",
        )

        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["id"], first.data["id"])
        self.assertEqual(PackagingSlip.objects.count(), 1)
        self.assertEqual(retry.data["slip_number"], first.data["slip_number"])

    def test_packaging_slip_requires_super_admin(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/admin/packaging-slips/",
            {"order_ids": [self.orders[0].id]},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_packaging_slip_rejects_empty_or_unknown_order_ids(self):
        self.client.force_authenticate(user=self.admin)

        empty = self.client.post(
            "/admin/packaging-slips/",
            {"order_ids": []},
            format="json",
        )
        unknown = self.client.post(
            "/admin/packaging-slips/",
            {"order_ids": [999999]},
            format="json",
        )

        self.assertEqual(empty.status_code, 400)
        self.assertEqual(unknown.status_code, 404)
