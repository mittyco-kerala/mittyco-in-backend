"""Backend-owned SKU generation for catalog variants and units."""

import re


def sku_part(value, limit=40):
    text = re.sub(r"[^A-Z0-9]+", "-", str(value or "").upper()).strip("-")
    return (text[:limit] or "PRODUCT")


def unique_sku(base, queryset, instance=None):
    root = sku_part(base, 88)
    candidate = root
    suffix = 2
    while queryset.filter(sku__iexact=candidate).exclude(
        pk=getattr(instance, "pk", None)
    ).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{root[:100 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def variant_sku_base(variant):
    product_name = sku_part(getattr(variant.product, "name", "PRODUCT"), 58)
    color = getattr(getattr(variant, "color", None), "name", None)
    if color:
        return f"MITTYCO-{product_name}-{sku_part(color, 24)}"
    position = variant.product.variants.exclude(pk=getattr(variant, "pk", None)).count() + 1
    return f"MITTYCO-{product_name}-V{position}"


def unit_sku_base(unit):
    variant = unit.variant
    product_name = sku_part(getattr(variant.product, "name", "PRODUCT"), 42)
    color = getattr(getattr(variant, "color", None), "name", None)
    unit_type = getattr(getattr(unit, "unit_type", None), "name", None)
    unit_name = getattr(getattr(unit, "unit", None), "name", None)
    parts = ["MITTYCO", product_name]
    if color:
        parts.append(sku_part(color, 20))
    if unit_type:
        parts.append(sku_part(unit_type, 18))
    if unit_name:
        parts.append(sku_part(unit_name, 24))
    return "-".join(parts)
