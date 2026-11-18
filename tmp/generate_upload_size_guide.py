from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak


ORANGE = colors.HexColor("#F97316")
ORANGE_DARK = colors.HexColor("#C2410C")
GREEN = colors.HexColor("#16A34A")
GREEN_DARK = colors.HexColor("#166534")
INK = colors.HexColor("#17202A")
MUTED = colors.HexColor("#5B6770")
PALE_ORANGE = colors.HexColor("#FFF7ED")
PALE_GREEN = colors.HexColor("#F0FDF4")
GRID = colors.HexColor("#D9E1E5")


GUIDE_ROWS = [
    ("Product card image", "Products > Variant > Add Image", "1200 x 1600 px", "3:4", "Portrait canvas for product cards. Keep the product centered with 8-12% empty space around it.", "JPEG / PNG / WebP"),
    ("Product detail image", "Products > Variant > Product images", "1200 x 1200 px", "1:1", "Square main-image canvas for the product detail page. The UI displays this image with contain, so the full product remains visible.", "JPEG / PNG / WebP"),
    ("Category image", "Catalog > Categories > Image", "1200 x 1200 px", "1:1", "Square canvas prevents unwanted crop in the shop category preview.", "JPEG / PNG / WebP"),
    ("Subcategory image", "Catalog > Subcategories > Image", "1200 x 1200 px", "1:1", "Same square crop behavior as the category preview.", "JPEG / PNG / WebP"),
    ("Brand logo", "Catalog > Brands > Logo", "1000 x 1000 px", "1:1", "Use a transparent PNG or WebP. Keep the logo inside the center 80% because the UI uses contain.", "PNG / WebP / JPEG"),
    ("Offer image", "Catalog > Offers > Offer image", "2400 x 500 px", "24:5", "Wide offer strip. Keep title, product, and discount text in the left/center safe area.", "JPEG / PNG / WebP"),
    ("Product promotional banner", "Products > Promotional & Social", "2400 x 440 px", "60:11", "Wide banner shown on the product detail page. Keep important content away from both edges.", "JPEG / PNG / WebP"),
    ("Hero banner", "Marketing > Hero Banners > Image", "1920 x 1080 px", "16:9", "Main homepage hero. Use a centered subject and keep text inside the center 70%; responsive cover crops on smaller screens.", "JPEG / PNG / WebP"),
]


def p(text: str, style: ParagraphStyle) -> Paragraph:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(escaped, style)


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=INK, spaceAfter=4),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=10),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=GREEN_DARK, spaceBefore=7, spaceAfter=5),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=INK),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=INK),
        "small_muted": ParagraphStyle("SmallMuted", parent=base["BodyText"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=MUTED),
        "small_center": ParagraphStyle("SmallCenter", parent=base["BodyText"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=INK, alignment=TA_CENTER),
        "small_right": ParagraphStyle("SmallRight", parent=base["BodyText"], fontName="Helvetica", fontSize=7.4, leading=9.2, textColor=INK, alignment=TA_RIGHT),
        "header": ParagraphStyle("Header", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.5, textColor=colors.white),
        "card_value": ParagraphStyle("CardValue", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=15, leading=17, textColor=INK, alignment=TA_CENTER),
        "card_label": ParagraphStyle("CardLabel", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2, leading=9, textColor=MUTED, alignment=TA_CENTER),
    }


def chrome(canvas, doc):
    canvas.saveState()
    width, height = landscape(A4)
    canvas.setFillColor(ORANGE)
    canvas.rect(0, height - 6, width, 6, fill=1, stroke=0)
    canvas.setFillColor(GREEN)
    canvas.rect(0, height - 8, width, 2, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(INK)
    canvas.drawString(18 * mm, height - 16 * mm, "MITTYCO DASHBOARD IMAGE UPLOAD GUIDE")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - 18 * mm, height - 16 * mm, "Recommended pixel sizes")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(18 * mm, 8 * mm, "Use these dimensions before uploading through the dashboard")
    canvas.drawRightString(width - 18 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def card(value: str, label: str, background: colors.Color, s):
    table = Table([[p(value, s["card_value"])], [p(label, s["card_label"])]], colWidths=[62 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background), ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    return table


def build(output: Path):
    s = styles()
    doc = SimpleDocTemplate(
        str(output), pagesize=landscape(A4), leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=23 * mm, bottomMargin=19 * mm,
        title="Mittyco Dashboard Image Upload Size Guide", author="Mittyco",
    )
    story = [Spacer(1, 5 * mm)]
    story.append(p("Dashboard Image Upload Size Guide", s["title"]))
    story.append(p("Use the exact recommended canvas size below when uploading images from the dashboard. These sizes are chosen from the current frontend card, banner, and responsive crop layouts.", s["subtitle"]))
    cards = Table([[
        card("8", "dashboard image types", PALE_ORANGE, s),
        card("5 MB", "maximum file size", PALE_GREEN, s),
        card("3", "accepted formats", PALE_ORANGE, s),
        card("center", "safe crop rule", PALE_GREEN, s),
    ]], colWidths=[65 * mm] * 4)
    cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    story.append(cards)
    story.append(Spacer(1, 5 * mm))
    story.append(p("Recommended upload sizes", s["section"]))
    headers = ["Image type", "Dashboard location", "Recommended canvas", "Ratio", "Fit guidance", "Format"]
    rows = [[p(item, s["header"]) for item in headers]]
    for row in GUIDE_ROWS:
        rows.append([
            p(row[0], s["small"]), p(row[1], s["small"]), p(row[2], s["small_center"]),
            p(row[3], s["small_center"]), p(row[4], s["small"]), p(row[5], s["small"]),
        ])
    table = Table(rows, colWidths=[34 * mm, 49 * mm, 37 * mm, 18 * mm, 82 * mm, 41 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE_DARK), ("GRID", (0, 0), (-1, -1), 0.35, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_ORANGE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(p("Important: the current backend validates file type and maximum size, but it does not yet enforce pixel dimensions. Treat the table as the production upload standard so images fit consistently across desktop and mobile.", s["body"]))

    story.append(PageBreak())
    story.append(p("Upload rules and crop safety", s["title"]))
    story.append(p("These rules prevent blur, unexpected cropping, stretched images, and oversized uploads.", s["subtitle"]))

    rules = [
        ("1. Resize first", "Create/export the image at the recommended canvas size before selecting it in the dashboard. Do not rely on the browser preview to resize it."),
        ("2. Keep the subject safe", "For product, category, and brand images, keep the important subject inside the center 80%. For wide banners, keep text and logos inside the center 70%."),
        ("3. Use the accepted formats", "The backend accepts JPEG, PNG, and WebP. Use PNG or WebP when transparency is needed for a brand logo. AVIF is not accepted by the dashboard upload validator."),
        ("4. Stay under the limit", "Each uploaded image must be 5 MB or smaller. WebP or JPEG quality around 80-85% is usually enough for photographs and banners."),
        ("5. Check both views", "After upload, check the homepage, shop/category page, product detail page, and mobile view. Hero, offer, and promotional banners use object-fit: cover and can crop edges."),
    ]
    rule_rows = []
    for heading, text in rules:
        rule_rows.append([p(heading, s["small"]), p(text, s["small"])])
    rule_table = Table(rule_rows, colWidths=[40 * mm, 221 * mm])
    rule_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE_GREEN), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(rule_table)
    story.append(Spacer(1, 6 * mm))
    story.append(p("Quick examples", s["section"]))
    examples = [
        [p("Product card photo", s["small_muted"]), p("1200 x 1600 px", s["small"]), p("Portrait product shot; centered; no important content near the edges.", s["small"])],
        [p("Product detail photo", s["small_muted"]), p("1200 x 1200 px", s["small"]), p("Square canvas; the full product remains visible in the detail-page gallery.", s["small"])],
        [p("Homepage hero", s["small_muted"]), p("1920 x 1080 px", s["small"]), p("Keep the subject and any text in the center safe area because mobile uses a different crop.", s["small"])],
    ]
    ex_table = Table(examples, colWidths=[40 * mm, 45 * mm, 176 * mm])
    ex_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE_ORANGE), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(ex_table)
    story.append(Spacer(1, 10 * mm))
    generated = datetime.now().astimezone().strftime("%d %b %Y, %I:%M %p %Z")
    story.append(p(f"Prepared from the current Mittyco dashboard upload fields and frontend display ratios. Generated: {generated}.", s["small_muted"]))
    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)


if __name__ == "__main__":
    output = Path(r"D:\mittyco-in-backend\output\pdf\mittyco-dashboard-image-upload-size-guide.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    build(output)
    print(output)
