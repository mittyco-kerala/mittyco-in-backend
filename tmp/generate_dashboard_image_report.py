from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp", ".tif", ".tiff"}
ORANGE = colors.HexColor("#F97316")
ORANGE_DARK = colors.HexColor("#C2410C")
GREEN = colors.HexColor("#16A34A")
GREEN_DARK = colors.HexColor("#166534")
INK = colors.HexColor("#17202A")
MUTED = colors.HexColor("#5B6770")
PALE_ORANGE = colors.HexColor("#FFF7ED")
PALE_GREEN = colors.HexColor("#F0FDF4")
GRID = colors.HexColor("#D9E1E5")


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB")
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(number)} B"
            return f"{number:.2f} {unit}"
        number /= 1024
    return f"{value} B"


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def image_dimensions(path: Path) -> tuple[str, str]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            return f"{width:,} x {height:,} px", "OK"
    except Exception as exc:  # Report the file instead of aborting the complete audit.
        return "-", f"Unreadable ({type(exc).__name__})"


def collect_records(upload_root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(upload_root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        dimensions, status = image_dimensions(path)
        size = path.stat().st_size
        records.append(
            {
                "path": path,
                "relative": path.relative_to(upload_root).as_posix(),
                "folder": path.parent.relative_to(upload_root).as_posix() or ".",
                "extension": path.suffix.lower().lstrip(".").upper(),
                "dimensions": dimensions,
                "status": status,
                "bytes": size,
            }
        )
    return records


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22,
            leading=26, textColor=INK, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=9.5,
            leading=13, textColor=MUTED, spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12,
            leading=15, textColor=GREEN_DARK, spaceBefore=8, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5,
            leading=11, textColor=INK,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2,
            leading=9, textColor=INK,
        ),
        "small_muted": ParagraphStyle(
            "SmallMuted", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2,
            leading=9, textColor=MUTED,
        ),
        "small_center": ParagraphStyle(
            "SmallCenter", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2,
            leading=9, textColor=INK, alignment=TA_CENTER,
        ),
        "small_right": ParagraphStyle(
            "SmallRight", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2,
            leading=9, textColor=INK, alignment=TA_RIGHT,
        ),
        "card_value": ParagraphStyle(
            "CardValue", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=14,
            leading=16, textColor=INK, alignment=TA_CENTER,
        ),
        "card_label": ParagraphStyle(
            "CardLabel", parent=base["BodyText"], fontName="Helvetica", fontSize=7.2,
            leading=9, textColor=MUTED, alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.2,
            leading=8.5, textColor=colors.white, alignment=TA_LEFT,
        ),
    }


def page_chrome(canvas, doc) -> None:
    canvas.saveState()
    width, height = landscape(A4)
    canvas.setFillColor(ORANGE)
    canvas.rect(0, height - 6, width, 6, fill=1, stroke=0)
    canvas.setFillColor(GREEN)
    canvas.rect(0, height - 8, width, 2, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(INK)
    canvas.drawString(18 * mm, height - 16 * mm, "MITTYCO DASHBOARD MEDIA AUDIT")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - 18 * mm, height - 16 * mm, "Orange + green report theme")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 8 * mm, "Source: dashboard media directory uploads/")
    canvas.drawRightString(width - 18 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def make_card(value: str, label: str, background: colors.Color, styles: dict[str, ParagraphStyle]) -> Table:
    card = Table([[paragraph(value, styles["card_value"])], [paragraph(label, styles["card_label"])]], colWidths=[62 * mm])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.6, GRID),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        )
    )
    return card


def build_pdf(records: list[dict[str, object]], upload_root: Path, output_pdf: Path) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    styles = build_styles()
    total_bytes = sum(int(record["bytes"]) for record in records)
    unreadable = sum(record["status"] != "OK" for record in records)
    extension_counts = Counter(str(record["extension"]) for record in records)
    folder_counts: defaultdict[str, int] = defaultdict(int)
    folder_bytes: defaultdict[str, int] = defaultdict(int)
    for record in records:
        folder = str(record["folder"])
        folder_counts[folder] += 1
        folder_bytes[folder] += int(record["bytes"])

    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=landscape(A4),
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=23 * mm, bottomMargin=19 * mm,
        title="Mittyco Dashboard Uploaded Images - Size and Pixel Dimensions",
        author="Mittyco",
    )
    story = []
    generated_at = datetime.now().astimezone().strftime("%d %b %Y, %I:%M %p %Z")
    story.append(Spacer(1, 5 * mm))
    story.append(paragraph("Dashboard Uploaded Images", styles["title"]))
    story.append(paragraph(
        "File size and pixel-dimension inventory for every raster image found under uploads/. "
        "Each file is listed separately, including files with similar names.", styles["subtitle"]
    ))

    cards = Table(
        [[
            make_card(f"{len(records):,}", "image files", PALE_ORANGE, styles),
            make_card(format_bytes(total_bytes), "total file size", PALE_GREEN, styles),
            make_card(f"{unreadable:,}", "unreadable files", PALE_ORANGE, styles),
            make_card(f"{len(folder_counts):,}", "upload folders", PALE_GREEN, styles),
        ]], colWidths=[65 * mm] * 4,
    )
    cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    story.append(cards)
    story.append(Spacer(1, 6 * mm))

    story.append(paragraph("Report scope", styles["section"]))
    scope_rows = [
        [paragraph("Source directory", styles["small_muted"]), paragraph("uploads/", styles["small"])],
        [paragraph("Generated", styles["small_muted"]), paragraph(generated_at, styles["small"])],
        [paragraph("Dimensions", styles["small_muted"]), paragraph("Width x height in pixels, read from each image file", styles["small"])],
        [paragraph("File size", styles["small_muted"]), paragraph("Actual file size shown using B, KB, MB, or GB", styles["small"])],
        [paragraph("Coverage", styles["small_muted"]), paragraph("JPG, JPEG, PNG, WEBP, AVIF, GIF, BMP, TIF, and TIFF files", styles["small"])],
    ]
    scope = Table(scope_rows, colWidths=[35 * mm, 217 * mm])
    scope.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE_ORANGE),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(scope)
    story.append(Spacer(1, 5 * mm))

    story.append(paragraph("File type summary", styles["section"]))
    extension_rows = [[paragraph("Type", styles["table_header"]), paragraph("Files", styles["table_header"]), paragraph("Total size", styles["table_header"])]]
    for extension in sorted(extension_counts):
        ext_records = [record for record in records if record["extension"] == extension]
        extension_rows.append([
            paragraph(extension, styles["small"]),
            paragraph(f"{len(ext_records):,}", styles["small_right"]),
            paragraph(format_bytes(sum(int(record["bytes"]) for record in ext_records)), styles["small_right"]),
        ])
    extension_table = Table(extension_rows, colWidths=[45 * mm, 35 * mm, 45 * mm], repeatRows=1)
    extension_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GREEN]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(extension_table)

    story.append(PageBreak())
    story.append(paragraph("Image inventory", styles["title"]))
    story.append(paragraph(
        "The table below is the complete file-by-file inventory. Pixel size is shown as width x height. "
        "Unreadable files remain listed so they can be corrected in the dashboard.", styles["subtitle"]
    ))

    headers = ["#", "Dashboard upload path", "Type", "Pixel size", "File size", "Status"]
    rows = [[paragraph(header, styles["table_header"]) for header in headers]]
    for index, record in enumerate(records, start=1):
        status = str(record["status"])
        status_style = styles["small"] if status == "OK" else ParagraphStyle("Error", parent=styles["small"], textColor=ORANGE_DARK)
        rows.append([
            paragraph(str(index), styles["small_center"]),
            paragraph(str(record["relative"]), styles["small"]),
            paragraph(str(record["extension"]), styles["small_center"]),
            paragraph(str(record["dimensions"]), styles["small_right"]),
            paragraph(format_bytes(int(record["bytes"])), styles["small_right"]),
            paragraph(status, status_style),
        ])
    inventory = Table(rows, colWidths=[12 * mm, 119 * mm, 19 * mm, 37 * mm, 30 * mm, 35 * mm], repeatRows=1, splitByRow=1)
    inventory.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE_DARK),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_ORANGE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(inventory)

    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a PDF inventory of dashboard uploaded images.")
    parser.add_argument("--uploads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    upload_root = args.uploads.resolve()
    if not upload_root.is_dir():
        raise SystemExit(f"uploads directory not found: {upload_root}")
    records = collect_records(upload_root)
    if not records:
        raise SystemExit("No supported raster image files found.")
    build_pdf(records, upload_root, args.output.resolve())
    print(f"Created {args.output.resolve()}")
    print(f"Images: {len(records)}")
    print(f"Total bytes: {sum(int(record['bytes']) for record in records)}")
    print(f"Unreadable: {sum(record['status'] != 'OK' for record in records)}")


if __name__ == "__main__":
    main()
