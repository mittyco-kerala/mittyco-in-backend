from django.db import migrations, models
from django.core.validators import MaxValueValidator, MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0036_productvariant_shipping_weight_grams_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                validators=[MinValueValidator(-90), MaxValueValidator(90)],
            ),
        ),
        migrations.AddField(
            model_name="address",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                validators=[MinValueValidator(-180), MaxValueValidator(180)],
            ),
        ),
    ]
