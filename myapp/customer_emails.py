"""Customer email notifications sent through the configured SMTP provider.

Mailtrap Sandbox can be selected through ``EMAIL_PROVIDER=mailtrap`` while
developing.  The helpers in this module deliberately do not include private
welcome-bonus assignment codes in email content.
"""

import logging
from decimal import Decimal, InvalidOperation
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .models import Invoice, Order, ProductVariant, User, WelcomeBonusAssignment


logger = logging.getLogger(__name__)


def _money(value):
    try:
        return Decimal(str(value or "0.00")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _site_url():
    return str(getattr(settings, "SITE_URL", "") or "").rstrip("/")


def _format_money(value):
    return f"₹{_money(value):,.2f}"


def _discount_text(bonus):
    if bonus.get("discount_type") == "FIXED":
        return f"₹{_money(bonus.get('fixed_amount')):,.2f} off"
    percentage = bonus.get("discount_percentage")
    return f"{percentage}% off" if percentage is not None else "special savings"


def _content(subject, text_body, html_body):
    return {"subject": subject, "text": text_body, "html": html_body}


def build_welcome_email(*, first_name, bonuses, site_url):
    """Build the registration email without exposing user-specific codes."""

    customer_name = str(first_name or "there").strip() or "there"
    bonus_list = list(bonuses or [])
    text_lines = [
        f"Hi {customer_name},",
        "",
        "Welcome to Mittyco! Your account has been created successfully.",
    ]
    if bonus_list:
        text_lines.extend(["", "Your welcome benefits:"])
        for bonus in bonus_list:
            end_date = bonus.get("end_date") or ""
            suffix = f" (valid until {end_date})" if end_date else ""
            text_lines.append(
                f"- {bonus.get('name') or 'Welcome bonus'}: "
                f"{bonus.get('discount_text') or 'special savings'}{suffix}"
            )
    else:
        text_lines.extend(["", "We will notify you when a welcome benefit is available."])
    text_lines.extend(["", f"Visit Mittyco: {site_url or 'the Mittyco store'}"])

    safe_name = escape(customer_name)
    safe_site_url = escape(site_url or "#", quote=True)
    bonus_rows = []
    for bonus in bonus_list:
        end_date = bonus.get("end_date") or ""
        validity = f" · valid until {escape(str(end_date))}" if end_date else ""
        bonus_rows.append(
            "<li style=\"margin:6px 0\">"
            f"<strong>{escape(str(bonus.get('name') or 'Welcome bonus'))}</strong>: "
            f"{escape(str(bonus.get('discount_text') or 'special savings'))}"
            f"{validity}</li>"
        )
    bonus_html = (
        "<h3>Your welcome benefits</h3><ul>" + "".join(bonus_rows) + "</ul>"
        if bonus_rows
        else "<p>We will notify you when a welcome benefit is available.</p>"
    )
    html_body = f"""
    <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#1f2937;max-width:640px\">
      <h2>Welcome to Mittyco</h2>
      <p>Hi {safe_name},</p>
      <p>Your account has been created successfully.</p>
      {bonus_html}
      <p><a href=\"{safe_site_url}\" style=\"display:inline-block;background:#1e654d;color:#fff;padding:12px 18px;border-radius:6px;text-decoration:none\">Visit Mittyco</a></p>
    </div>
    """
    return _content("Welcome to Mittyco", "\n".join(text_lines), html_body)


def build_pending_payment_email(*, customer_name, provider, reference, amount, items, site_url):
    """Build the payment-started email for a checkout that is not paid yet."""

    item_list = list(items or [])
    text_lines = [
        f"Hi {customer_name or 'there'},",
        "",
        "Your Mittyco order has been created and payment is pending.",
        f"Payment provider: {provider}",
        f"Payment reference: {reference}",
        f"Amount: {_format_money(amount)}",
        "",
        "Items:",
    ]
    text_lines.extend(
        f"- {item.get('name') or 'Product'} x {item.get('quantity', 1)} = {_format_money(item.get('total'))}"
        for item in item_list
    )
    text_lines.extend(
        [
            "",
            "This is not a paid invoice. We will send the invoice after payment is verified.",
            f"Visit Mittyco: {site_url or 'the Mittyco store'}",
        ]
    )

    safe_name = escape(str(customer_name or "there"))
    safe_provider = escape(str(provider or "Online payment"))
    safe_reference = escape(str(reference or ""))
    item_rows = "".join(
        "<tr>"
        f"<td style=\"padding:8px 0\">{escape(str(item.get('name') or 'Product'))}</td>"
        f"<td style=\"padding:8px 0;text-align:center\">{int(item.get('quantity') or 1)}</td>"
        f"<td style=\"padding:8px 0;text-align:right\">{escape(_format_money(item.get('total')))}</td>"
        "</tr>"
        for item in item_list
    )
    html_body = f"""
    <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#1f2937;max-width:640px\">
      <h2>Mittyco payment pending</h2>
      <p>Hi {safe_name},</p>
      <p>Your order has been created, but payment is still pending.</p>
      <p><strong>Provider:</strong> {safe_provider}<br><strong>Reference:</strong> {safe_reference}<br><strong>Amount:</strong> {escape(_format_money(amount))}</p>
      <table style=\"width:100%;border-collapse:collapse\"><thead><tr style=\"border-bottom:1px solid #d1d5db\"><th style=\"text-align:left;padding:8px 0\">Item</th><th style=\"text-align:center;padding:8px 0\">Qty</th><th style=\"text-align:right;padding:8px 0\">Amount</th></tr></thead><tbody>{item_rows or '<tr><td colspan=\"3\">No items recorded</td></tr>'}</tbody></table>
      <p>This is not a paid invoice. We will send the invoice after payment is verified.</p>
      <p><a href=\"{escape(site_url or '#', quote=True)}\">Visit Mittyco</a></p>
    </div>
    """
    return _content("Mittyco payment pending", "\n".join(text_lines), html_body)


def build_invoice_email(*, customer_name, order_number, invoice_number, issued_at, payment_method, total, items, site_url):
    """Build the paid-order invoice email."""

    item_list = list(items or [])
    text_lines = [
        f"Hi {customer_name or 'there'},",
        "",
        "Your Mittyco payment was successful and your order is confirmed.",
        f"Order: {order_number}",
        f"Invoice: {invoice_number}",
        f"Issued: {issued_at}",
        f"Payment method: {payment_method}",
        "Payment status: Paid",
        "",
        "Items:",
    ]
    text_lines.extend(
        f"- {item.get('name') or 'Product'} x {item.get('quantity', 1)} = {_format_money(item.get('total'))}"
        for item in item_list
    )
    text_lines.extend(["", f"Total: {_format_money(total)}", f"Visit Mittyco: {site_url or 'the Mittyco store'}"])

    safe_name = escape(str(customer_name or "there"))
    safe_order = escape(str(order_number))
    safe_invoice = escape(str(invoice_number))
    item_rows = "".join(
        "<tr>"
        f"<td style=\"padding:8px 0\">{escape(str(item.get('name') or 'Product'))}</td>"
        f"<td style=\"padding:8px 0;text-align:center\">{int(item.get('quantity') or 1)}</td>"
        f"<td style=\"padding:8px 0;text-align:right\">{escape(_format_money(item.get('total')))}</td>"
        "</tr>"
        for item in item_list
    )
    html_body = f"""
    <div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#1f2937;max-width:640px\">
      <h2>Mittyco invoice</h2>
      <p>Hi {safe_name},</p>
      <p>Your payment was successful and your order is confirmed.</p>
      <p><strong>Order:</strong> {safe_order}<br><strong>Invoice:</strong> {safe_invoice}<br><strong>Payment status:</strong> Paid</p>
      <table style=\"width:100%;border-collapse:collapse\"><thead><tr style=\"border-bottom:1px solid #d1d5db\"><th style=\"text-align:left;padding:8px 0\">Item</th><th style=\"text-align:center;padding:8px 0\">Qty</th><th style=\"text-align:right;padding:8px 0\">Amount</th></tr></thead><tbody>{item_rows or '<tr><td colspan=\"3\">No items recorded</td></tr>'}</tbody></table>
      <p><strong>Total:</strong> {escape(_format_money(total))}<br><strong>Payment method:</strong> {escape(str(payment_method or 'Online payment'))}</p>
      <p><a href=\"{escape(site_url or '#', quote=True)}\">Visit Mittyco</a></p>
    </div>
    """
    return _content(f"Invoice {invoice_number} from Mittyco", "\n".join(text_lines), html_body)


def _send_content(content, recipient, *, reply_to=None):
    recipient = str(recipient or "").strip()
    if not recipient:
        logger.warning("Customer email skipped: recipient email is empty")
        return False
    message = EmailMultiAlternatives(
        subject=content["subject"],
        body=content["text"],
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[recipient],
        reply_to=[reply_to] if reply_to else [],
    )
    message.attach_alternative(content["html"], "text/html")
    try:
        message.send(fail_silently=False)
    except Exception:
        logger.exception("Customer email failed for %s", recipient)
        return False
    logger.info("Customer email sent to %s: %s", recipient, content["subject"])
    return True


def send_welcome_email(user_id):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error("Welcome email skipped: user %s not found", user_id)
        return False

    now = timezone.now()
    assignments = (
        WelcomeBonusAssignment.objects.select_related("welcome_bonus")
        .filter(
            user_id=user.id,
            status__in=(
                WelcomeBonusAssignment.STATUS_AVAILABLE,
                WelcomeBonusAssignment.STATUS_CLAIMED,
            ),
            welcome_bonus__is_active=True,
            welcome_bonus__archived_at__isnull=True,
            welcome_bonus__start_date__lte=now,
            welcome_bonus__end_date__gte=now,
        )
        .order_by("welcome_bonus__end_date", "welcome_bonus__name")
    )
    bonuses = []
    for assignment in assignments:
        bonus = assignment.welcome_bonus
        bonuses.append(
            {
                "name": bonus.name,
                "discount_type": bonus.discount_type,
                "discount_percentage": bonus.discount_percentage,
                "fixed_amount": bonus.fixed_amount,
                "discount_text": _discount_text(
                    {
                        "discount_type": bonus.discount_type,
                        "discount_percentage": bonus.discount_percentage,
                        "fixed_amount": bonus.fixed_amount,
                    }
                ),
                "end_date": timezone.localtime(bonus.end_date).strftime("%d %b %Y"),
            }
        )
    content = build_welcome_email(
        first_name=user.first_name or user.get_full_name(),
        bonuses=bonuses,
        site_url=_site_url(),
    )
    return _send_content(content, user.email)


def _snapshot_items(snapshot):
    products = list((snapshot or {}).get("products") or [])
    variant_ids = [item.get("variant_id") for item in products if item.get("variant_id")]
    variants = ProductVariant.objects.select_related("product").in_bulk(variant_ids)
    items = []
    for item in products:
        variant = variants.get(item.get("variant_id"))
        price = _money(item.get("price"))
        quantity = int(item.get("quantity") or 1)
        items.append(
            {
                "name": variant.product.name if variant and variant.product_id else "Product",
                "quantity": quantity,
                "total": price * quantity,
            }
        )
    return items


def send_pending_payment_email(checkout, *, provider):
    user = getattr(checkout, "user", None)
    if not user or not user.email:
        return False
    reference = getattr(checkout, "razorpay_order_id", None) or getattr(
        checkout, "cashfree_order_id", ""
    )
    content = build_pending_payment_email(
        customer_name=user.get_full_name() or user.email.split("@", 1)[0],
        provider=provider,
        reference=reference,
        amount=checkout.amount,
        items=_snapshot_items(checkout.snapshot),
        site_url=_site_url(),
    )
    return _send_content(content, user.email)


def send_paid_invoice_email(order_id):
    try:
        order = (
            Order.objects.select_related("user", "invoice")
            .prefetch_related("items__product")
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        logger.error("Invoice email skipped: order %s not found", order_id)
        return False

    if order.payment_status != "Paid":
        logger.warning("Invoice email skipped: order %s is not paid", order_id)
        return False

    invoice = getattr(order, "invoice", None)
    if invoice is None:
        invoice, _ = Invoice.objects.get_or_create(
            order=order,
            defaults={"invoice_number": f"INV-{order.pk:06d}"},
        )
    address = order.address
    customer_name = (
        (address.full_name if address else "")
        or order.user.get_full_name()
        or order.user.email.split("@", 1)[0]
    )
    items = [
        {
            "name": item.product.name if item.product_id else "Product",
            "quantity": item.quantity,
            "total": item.total_price,
        }
        for item in order.items.all()
    ]
    issued_at = timezone.localtime(invoice.issued_at).strftime("%d %b %Y, %I:%M %p")
    content = build_invoice_email(
        customer_name=customer_name,
        order_number=f"ORD-{order.pk:06d}",
        invoice_number=invoice.invoice_number,
        issued_at=issued_at,
        payment_method=order.get_payment_method_display(),
        total=order.total_amount,
        items=items,
        site_url=_site_url(),
    )
    return _send_content(content, order.user.email, reply_to=None)
