from decimal import Decimal

from django.test import TestCase

from .models import (
    Category,
    Color,
    Product,
    ProductVariant,
    ProductVariantUnit,
    SubCategory,
    Unit,
    UnitType,
)
from .serializers import HomepageProductSerializer


class HomepageProductUrlMetadataTests(TestCase):
    def test_default_variant_metadata_is_available_for_product_urls(self):
        category = Category.objects.create(name="Oils", image="oils.jpg")
        subcategory = SubCategory.objects.create(category=category, name="Coconut oil")
        unit_type = UnitType.objects.create(name="Volume")
        unit = Unit.objects.create(unit_type=unit_type, name="1 L")
        color = Color.objects.create(name="Natural", code="#ffffff")
        product = Product.objects.create(
            category=category,
            subcategory=subcategory,
            name="Cold Pressed Coconut Oil",
            description="Coconut oil",
        )
        variant = ProductVariant.objects.create(
            product=product,
            color=color,
            price_type="multiple",
        )
        ProductVariantUnit.objects.create(
            variant=variant,
            unit_type=unit_type,
            unit=unit,
            price=Decimal("25.50"),
            stock=3,
        )

        payload = HomepageProductSerializer(product).data

        self.assertEqual(payload["default_color_name"], "Natural")
        self.assertEqual(payload["default_unit_type_name"], "Volume")
        self.assertEqual(payload["default_unit_name"], "1 L")
