from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("myapp", "0038_order_prodinent_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_quote",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="order",
            name="fulfillment_provider",
            field=models.CharField(
                choices=[("prodinent", "Prodinent"), ("india_post", "India Post API")],
                default="prodinent",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_barcode",
            field=models.CharField(blank=True, max_length=13, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_booking_status",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_booking_reference",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_contract_id",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_booking_office_id",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_booking_office_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_dropoff_pincode",
            field=models.CharField(blank=True, max_length=6),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_booking_attempted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_booked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_tracking_status",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_tracking_events",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_tracking_last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="india_post_last_error",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="IndiaPostBarcodeSeries",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("article_type", models.CharField(default="BP", max_length=2)),
                ("contract_id", models.CharField(max_length=8)),
                ("barcode_prefix", models.CharField(max_length=2)),
                ("allocation_start", models.PositiveIntegerField(blank=True, null=True)),
                ("next_number", models.PositiveIntegerField()),
                ("last_number", models.PositiveIntegerField()),
                ("booking_office_id", models.CharField(max_length=8)),
                ("booking_office_name", models.CharField(max_length=100)),
                ("dropoff_pincode", models.CharField(max_length=6)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("created_at", "id")},
        ),
    ]
