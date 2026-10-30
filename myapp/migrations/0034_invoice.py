from django.db import migrations, models
import django.db.models.deletion


def issue_existing_paid_order_invoices(apps, schema_editor):
    Order = apps.get_model("myapp", "Order")
    Invoice = apps.get_model("myapp", "Invoice")
    for order in Order.objects.filter(payment_status="Paid").iterator():
        Invoice.objects.get_or_create(
            order_id=order.pk,
            defaults={"invoice_number": f"INV-{order.pk:06d}"},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("myapp", "0033_offer_discount_type_offer_fixed_amount_offer_product_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Invoice",
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
                ("invoice_number", models.CharField(max_length=32, unique=True)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoice",
                        to="myapp.order",
                    ),
                ),
            ],
            options={"ordering": ("-issued_at", "-id")},
        ),
        migrations.RunPython(
            issue_existing_paid_order_invoices,
            migrations.RunPython.noop,
        ),
    ]
