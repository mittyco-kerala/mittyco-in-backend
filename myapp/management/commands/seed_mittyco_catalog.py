from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from myapp.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    ProductVariantUnit,
    SubCategory,
    Unit,
    UnitType,
)


ASSET_DIR = Path(__file__).resolve().parents[3] / "seed_mittyco_assets"


PICKLE_DEFAULT_IMAGES = [
    "mittyco-pickle-studio.png",
    "pickle-range.jpeg",
    "mittyco-pickle-meal.png",
]

PICKLE_IMAGES = {
    "Mango": ["mango-pickle-label.jpeg", "mittyco-pickle-studio.png", "mittyco-pickle-meal.png"],
    "Lemon": ["lemon-pickle-label.jpeg", "mittyco-pickle-studio.png", "mittyco-pickle-meal.png"],
    "Garlic": ["garlic-pickle-product.jpeg", "garlic-pickle-label.jpeg", "mittyco-pickle-meal.png"],
}

COCONUT_IMAGES = {
    "Hot": ["coconut-oil-hot.jpeg", "coconut-oil-hot-label.jpeg", "mittyco-coconut-studio.png"],
    "Cold": ["coconut-oil-cold.jpeg", "coconut-oil-cold-label.jpeg", "mittyco-coconut-studio.png"],
}


PRODUCTS = [
    {
        "name": "Mittyco Homemade Mango Pickle",
        "kind": "pickle",
        "flavour": "Mango",
        "description": "Homemade mango pickle prepared in small batches with ripe mango pieces and traditional Kerala spices.",
        "prices": (180, 320, 580),
        "sku": "MANGO",
    },
    {
        "name": "Mittyco Homemade Lemon Pickle",
        "kind": "pickle",
        "flavour": "Lemon",
        "description": "Bright, tangy homemade lemon pickle with a balanced blend of spices for everyday meals.",
        "prices": (170, 300, 540),
        "sku": "LEMON",
    },
    {
        "name": "Mittyco Homemade Garlic Pickle",
        "kind": "pickle",
        "flavour": "Garlic",
        "description": "A bold homemade garlic pickle made with whole garlic cloves, sesame oil, and Kerala spices.",
        "prices": (190, 340, 620),
        "sku": "GARLIC",
    },
    {
        "name": "Mittyco Homemade Ginger Pickle",
        "kind": "pickle",
        "flavour": "Ginger",
        "description": "Homemade ginger pickle with a warm, spicy flavour that pairs beautifully with rice and traditional meals.",
        "prices": (180, 320, 580),
        "sku": "GINGER",
    },
    {
        "name": "Mittyco Homemade Green Chilli Pickle",
        "kind": "pickle",
        "flavour": "Green Chilli",
        "description": "Fresh green chilli pickle made with aromatic spices for a lively and savoury accompaniment.",
        "prices": (180, 320, 580),
        "sku": "GREEN-CHILLI",
    },
    {
        "name": "Mittyco Homemade Mixed Vegetable Pickle",
        "kind": "pickle",
        "flavour": "Mixed Vegetable",
        "description": "A colourful mix of vegetables seasoned with homemade pickle spices and sesame oil.",
        "prices": (180, 320, 580),
        "sku": "MIXED-VEG",
    },
    {
        "name": "Mittyco Homemade Chicken Pickle",
        "kind": "pickle",
        "flavour": "Chicken",
        "description": "Rich and spicy homemade chicken pickle prepared as a traditional non-vegetarian accompaniment.",
        "prices": (220, 390, 720),
        "sku": "CHICKEN",
    },
    {
        "name": "Mittyco Homemade Dry Fish Pickle",
        "kind": "pickle",
        "flavour": "Dry Fish",
        "description": "Traditional dry fish pickle with a deep savoury flavour and a carefully balanced spice blend.",
        "prices": (240, 430, 780),
        "sku": "DRY-FISH",
    },
    {
        "name": "Mittyco Homemade Dates Kondattam Pickle",
        "kind": "pickle",
        "flavour": "Dates Kondattam",
        "description": "A distinctive homemade dates kondattam pickle with a rich texture and Kerala-style seasoning.",
        "prices": (200, 360, 650),
        "sku": "DATES-KONDATTAM",
    },
    {
        "name": "Mittyco Homemade Tender Mango Pickle",
        "kind": "pickle",
        "flavour": "Tender Mango",
        "description": "Tender mango pieces preserved with traditional spices for a crisp, tangy side dish.",
        "prices": (180, 320, 580),
        "sku": "TENDER-MANGO",
    },
    {
        "name": "Mittyco Homemade Gooseberry Pickle",
        "kind": "pickle",
        "flavour": "Gooseberry",
        "description": "Homemade gooseberry pickle with a bright, tangy taste and a traditional spice finish.",
        "prices": (190, 340, 620),
        "sku": "GOOSEBERRY",
    },
    {
        "name": "Mittyco Homemade Carrot & Beetroot Pickle",
        "kind": "pickle",
        "flavour": "Carrot & Beetroot",
        "description": "A vibrant homemade pickle made with carrot and beetroot, seasoned for a balanced sweet and spicy bite.",
        "prices": (180, 320, 580),
        "sku": "CARROT-BEETROOT",
    },
    {
        "name": "Mittyco Hot Processed Virgin Coconut Oil",
        "kind": "coconut",
        "flavour": "Hot",
        "description": "Mittyco hot processed virgin coconut oil made from coconut milk using a traditional boiling method.",
        "prices": (240, 420, 780),
        "sku": "HOT-OIL",
    },
    {
        "name": "Mittyco Cold Pressed Coconut Oil",
        "kind": "coconut",
        "flavour": "Cold",
        "description": "Mittyco cold pressed coconut oil made from carefully selected copra with a clean, natural finish.",
        "prices": (290, 520, 960),
        "sku": "COLD-OIL",
    },
    {
        "name": "Mittyco Hot Processed Coconut Oil Family Pack",
        "kind": "coconut",
        "flavour": "Hot",
        "description": "A value-focused family pack of Mittyco hot processed virgin coconut oil for regular kitchen use.",
        "prices": (260, 470, 880),
        "sku": "HOT-OIL-FAMILY",
    },
    {
        "name": "Mittyco Cold Pressed Coconut Oil Family Pack",
        "kind": "coconut",
        "flavour": "Cold",
        "description": "A larger family pack of Mittyco cold pressed coconut oil for everyday cooking and pantry use.",
        "prices": (320, 580, 1080),
        "sku": "COLD-OIL-FAMILY",
    },
    {
        "name": "Mittyco Hot Processed Coconut Oil Trial Pack",
        "kind": "coconut",
        "flavour": "Hot",
        "description": "A convenient smaller-size selection of Mittyco hot processed virgin coconut oil.",
        "prices": (230, 400, 740),
        "sku": "HOT-OIL-TRIAL",
    },
    {
        "name": "Mittyco Cold Pressed Coconut Oil Trial Pack",
        "kind": "coconut",
        "flavour": "Cold",
        "description": "A convenient smaller-size selection of Mittyco cold pressed coconut oil.",
        "prices": (280, 500, 920),
        "sku": "COLD-OIL-TRIAL",
    },
    {
        "name": "Mittyco Coconut Oil Duo Pack",
        "kind": "coconut",
        "flavour": "Cold",
        "description": "A Mittyco duo pack bringing hot processed and cold pressed coconut oil options together.",
        "prices": (300, 540, 1000),
        "sku": "OIL-DUO",
    },
    {
        "name": "Mittyco Coconut Oil Gift Pack",
        "kind": "coconut",
        "flavour": "Hot",
        "description": "A neatly presented Mittyco coconut oil selection suitable for gifting and home use.",
        "prices": (320, 580, 1080),
        "sku": "OIL-GIFT",
    },
]


class Command(BaseCommand):
    help = "Create or refresh the 20-product Mittyco pickle and coconut oil catalog."

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset-dir",
            default=str(ASSET_DIR),
            help="Directory containing the supplied and generated Mittyco product images.",
        )

    def handle(self, *args, **options):
        asset_dir = Path(options["asset_dir"]).resolve()
        required = {
            filename
            for product in PRODUCTS
            for filename in self._images_for(product)
        }
        missing = sorted(filename for filename in required if not (asset_dir / filename).exists())
        if missing:
            raise CommandError("Missing product image assets: " + ", ".join(missing))

        with transaction.atomic():
            brand = Brand.objects.filter(name="Mittyco").first()
            if not brand:
                brand = Brand.objects.create(name="Mittyco", slug="mittyco", is_active=True)

            pickle_category = self._category("Pickles", "pickle-range.jpeg")
            pickle_subcategory = self._subcategory(pickle_category, "Homemade Pickles")
            coconut_category = self._category("Coconut Oil", "coconut-oil-hot.jpeg")
            coconut_subcategory = self._subcategory(coconut_category, "Coconut Oils")

            weight_type, _ = UnitType.objects.get_or_create(name="Weight")
            volume_type, _ = UnitType.objects.get_or_create(name="Volume")
            weight_units = self._units(weight_type, (("250 g", 250), ("500 g", 500), ("1 KG", 1000)))
            volume_units = self._units(volume_type, (("250 ML", 250), ("500 ML", 500), ("1 L", 1000)))

            for product_index, spec in enumerate(PRODUCTS, start=1):
                category = pickle_category if spec["kind"] == "pickle" else coconut_category
                subcategory = pickle_subcategory if spec["kind"] == "pickle" else coconut_subcategory
                product = Product.objects.filter(name=spec["name"]).first()
                if product is None:
                    product = Product(name=spec["name"])
                product.category = category
                product.subcategory = subcategory
                product.brand = brand
                product.description = spec["description"]
                product.is_active = True
                product.key_features = self._features(spec)
                product.shipping_fee = 0
                product.estimated_delivery_time = "3–5 business days"
                product.seller_name = "Mittyco Production & Packaging unit"
                product.warranty_info = ""
                product.related_product_mode = Product.RELATED_PRODUCT_MODE_NONE
                product.save()

                # Refresh only this named catalog product so the command is safe to rerun.
                ProductVariant.objects.filter(product=product).delete()
                unit_type = weight_type if spec["kind"] == "pickle" else volume_type
                units = weight_units if spec["kind"] == "pickle" else volume_units
                variant = ProductVariant.objects.create(
                    product=product,
                    sku=f"MIT-{spec['sku']}",
                    price_type="multiple",
                    price=None,
                    stock=0,
                )
                for unit_index, (unit, price) in enumerate(zip(units, spec["prices"]), start=1):
                    ProductVariantUnit.objects.create(
                        variant=variant,
                        unit_type=unit_type,
                        unit=unit,
                        sku=f"MIT-{spec['sku']}-{unit_index}",
                        price=price,
                        stock=40 if unit_index == 1 else 25 if unit_index == 2 else 12,
                    )
                for image_index, image_name in enumerate(self._images_for(spec)):
                    source = asset_dir / image_name
                    with source.open("rb") as image_file:
                        ProductImage.objects.create(
                            variant=variant,
                            image=File(image_file, name=image_name),
                            is_primary=image_index == 0,
                            position=image_index,
                        )
                self.stdout.write(self.style.SUCCESS(f"[{product_index:02d}/20] {product.name}"))

        self.stdout.write(self.style.SUCCESS("Mittyco catalog ready: 20 products, 60 product images, and 60 unit prices."))

    def _images_for(self, spec):
        if spec["kind"] == "pickle":
            return PICKLE_IMAGES.get(spec["flavour"], PICKLE_DEFAULT_IMAGES)
        return COCONUT_IMAGES[spec["flavour"]]

    def _features(self, spec):
        if spec["kind"] == "pickle":
            return "Homemade Kerala-style pickle\nSmall-batch preparation\nAvailable in 250 g, 500 g and 1 KG packs"
        return "Mittyco coconut oil range\nCarefully packed in Kerala\nAvailable in 250 ML, 500 ML and 1 L packs"

    def _category(self, name, image_name):
        category, _ = Category.objects.get_or_create(name=name, defaults={"is_active": True})
        if not category.image:
            source = ASSET_DIR / image_name
            with source.open("rb") as image_file:
                category.image.save(image_name, File(image_file), save=True)
        return category

    def _subcategory(self, category, name):
        subcategory, _ = SubCategory.objects.get_or_create(category=category, name=name)
        subcategory.is_active = True
        subcategory.save(update_fields=["is_active"])
        return subcategory

    def _units(self, unit_type, definitions):
        return [
            Unit.objects.get_or_create(unit_type=unit_type, name=name)[0]
            for name, _ in definitions
        ]
