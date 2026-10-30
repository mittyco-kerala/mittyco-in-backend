from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("myapp", "0032_order_payment_method"),
        ("payment", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RazorpayCheckout",
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
                    "razorpay_order_id",
                    models.CharField(max_length=255, unique=True),
                ),
                (
                    "idempotency_key",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        unique=True,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(max_length=3)),
                ("snapshot", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Created", "Created"),
                            ("Active", "Active"),
                            ("Paid", "Paid"),
                            ("Fulfilled", "Fulfilled"),
                            ("Failed", "Failed"),
                            ("Fulfillment Error", "Fulfillment Error"),
                        ],
                        default="Created",
                        max_length=30,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "address",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="razorpay_checkouts",
                        to="myapp.address",
                    ),
                ),
                (
                    "order",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="razorpay_checkout",
                        to="myapp.order",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="razorpay_checkouts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "status"], name="payment_raz_user_id_617270_idx"),
                    models.Index(fields=["created_at"], name="payment_raz_created_adc509_idx"),
                ],
            },
        ),
    ]
