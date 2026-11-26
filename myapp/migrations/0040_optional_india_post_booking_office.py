from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0039_india_post_direct_fulfillment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="indiapostbarcodeseries",
            name="booking_office_id",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AlterField(
            model_name="indiapostbarcodeseries",
            name="booking_office_name",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="indiapostbarcodeseries",
            name="dropoff_pincode",
            field=models.CharField(blank=True, default="", max_length=6),
        ),
    ]
