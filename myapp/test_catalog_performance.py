from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient

from .models import Brand, Category, Color, Product, ProductVariant, SubCategory


class PublicCatalogQueryBudgetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        category = Category.objects.create(name="Catalog", image="categories/catalog.png")
        subcategory = SubCategory.objects.create(
            category=category,
            name="General",
            image="subcategories/general.png",
        )
        brand = Brand.objects.create(name="Mittyco")
        color = Color.objects.create(name="Blue", code="#0000FF")
        for index in range(2):
            product = Product.objects.create(
                category=category,
                subcategory=subcategory,
                brand=brand,
                name=f"Product {index}",
                description="Catalog product",
            )
            ProductVariant.objects.create(
                product=product,
                color=color,
                price_type="single",
                price="100.00",
                stock=10,
            )

    def test_product_list_stays_within_a_fixed_query_budget(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/products/?page_size=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertLessEqual(
            len(queries),
            12,
            f"Public product listing executed {len(queries)} queries",
        )
