from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0037_address_delivery_coordinates"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="prodinent_article_id",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="prodinent_label_available",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="order",
            name="prodinent_last_error",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="prodinent_order_id",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="prodinent_status",
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="prodinent_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="prodinent_tracking_link",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
