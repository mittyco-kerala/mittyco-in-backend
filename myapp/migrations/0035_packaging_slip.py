from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0034_invoice"),
    ]

    operations = [
        migrations.CreateModel(
            name="PackagingSlip",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slip_number",
                    models.CharField(editable=False, max_length=32, unique=True),
                ),
                (
                    "order_set_key",
                    models.CharField(
                        blank=True,
                        editable=False,
                        max_length=512,
                        null=True,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_packaging_slips",
                        to="myapp.user",
                    ),
                ),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="PackagingSlipItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "barcode",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "order_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="packaging_slip_items",
                        to="myapp.orderitem",
                    ),
                ),
                (
                    "slip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="myapp.packagingslip",
                    ),
                ),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.AddConstraint(
            model_name="packagingslipitem",
            constraint=models.UniqueConstraint(
                fields=("slip", "order_item"),
                name="myapp_packaging_slip_order_item_unique",
            ),
        ),
        migrations.AddField(
            model_name="packagingslip",
            name="orders",
            field=models.ManyToManyField(
                blank=True,
                related_name="packaging_slips",
                to="myapp.order",
            ),
        ),
    ]
