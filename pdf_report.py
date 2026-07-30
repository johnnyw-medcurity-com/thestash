import io
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image as RLImage,
    PageBreak,
)

from categories import NEEDS_REVIEW_CATEGORY

NAVY = colors.HexColor("#1e293b")
RED = colors.HexColor("#dc2626")
LIGHT_GRAY = colors.HexColor("#f1f5f9")

RECEIPT_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
RECEIPT_CELL_WIDTH = 2.9 * inch
RECEIPT_CELL_MAX_HEIGHT = 3.4 * inch


def _fmt_money(amount):
    return f"${amount:,.2f}"


def _fmt_date(value):
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return value


def _build_receipt_cell(path, caption_text, caption_style):
    try:
        with PILImage.open(path) as im:
            width_px, height_px = im.size
    except Exception:
        return [Paragraph(caption_text, caption_style), Paragraph("<i>(receipt image could not be loaded)</i>", caption_style)]

    aspect = (height_px / width_px) if width_px else 1
    img_width = RECEIPT_CELL_WIDTH
    img_height = img_width * aspect
    if img_height > RECEIPT_CELL_MAX_HEIGHT:
        img_height = RECEIPT_CELL_MAX_HEIGHT
        img_width = img_height / aspect

    try:
        rl_img = RLImage(str(path), width=img_width, height=img_height)
    except Exception:
        return [Paragraph(caption_text, caption_style), Paragraph("<i>(receipt image could not be loaded)</i>", caption_style)]

    return [rl_img, Spacer(1, 4), Paragraph(caption_text, caption_style)]


def build_trip_pdf(trip, client_name, user_name, user_email, expenses, upload_dir=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Title"], textColor=NAVY, fontSize=18, spaceAfter=2
    )
    meta_style = ParagraphStyle(
        "MetaStyle", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#475569")
    )
    section_style = ParagraphStyle(
        "SectionStyle", parent=styles["Heading2"], textColor=NAVY, fontSize=12, spaceBefore=14, spaceAfter=6
    )
    warn_style = ParagraphStyle(
        "WarnStyle", parent=styles["Normal"], fontSize=9, textColor=RED
    )

    story = []
    story.append(Paragraph("Travel Expense Report", title_style))
    story.append(Spacer(1, 6))

    meta_rows = [
        ["Client:", client_name or "—"],
        ["Employee:", f"{user_name} ({user_email})"],
        ["Trip Purpose:", trip["purpose"] or "—"],
        ["Dates:", f"{_fmt_date(trip['start_date'])} – {_fmt_date(trip['end_date'])}"],
        ["Status:", (trip["status"] or "draft").title()],
        ["Generated:", datetime.now().strftime("%b %d, %Y %I:%M %p")],
    ]
    meta_table = Table(meta_rows, colWidths=[1.3 * inch, 5 * inch])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(meta_table)

    story.append(Paragraph("Itemized Expenses", section_style))

    header = ["Date", "Category", "Vendor", "Amount", "Notes"]
    rows = [header]
    flagged_rows = []
    category_totals = OrderedDict()
    grand_total = 0.0

    for exp in expenses:
        amount = exp["amount"] or 0.0
        grand_total += amount
        category_totals.setdefault(exp["category"], 0.0)
        category_totals[exp["category"]] += amount

        note = exp["notes"] or ""
        if exp["flagged"]:
            note = ("⚠ " + note).strip()
        rows.append(
            [
                _fmt_date(exp["date"]),
                exp["category"],
                exp["vendor"] or "",
                _fmt_money(amount),
                note,
            ]
        )
        if exp["flagged"]:
            flagged_rows.append(exp)

    table = Table(rows, colWidths=[0.9 * inch, 1.7 * inch, 1.3 * inch, 0.8 * inch, 1.6 * inch], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i, exp in enumerate(expenses, start=1):
        if exp["flagged"]:
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), RED))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)

    story.append(Spacer(1, 12))
    story.append(Paragraph("Summary by Category", section_style))
    summary_rows = [["Category", "Subtotal"]]
    for cat, total in category_totals.items():
        summary_rows.append([cat, _fmt_money(total)])
    summary_rows.append(["Grand Total", _fmt_money(grand_total)])
    summary_table = Table(summary_rows, colWidths=[4 * inch, 2.3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GRAY),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(summary_table)

    if flagged_rows:
        story.append(Spacer(1, 14))
        story.append(Paragraph("⚠ Flagged for Review", section_style))
        story.append(
            Paragraph(
                "The items below were flagged by the submitter as unsure whether they qualify "
                "as a covered business expense. Please review before reimbursing.",
                warn_style,
            )
        )
        story.append(Spacer(1, 4))
        flag_rows = [["Date", "Category", "Vendor", "Amount", "Notes"]]
        for exp in flagged_rows:
            flag_rows.append(
                [
                    _fmt_date(exp["date"]),
                    exp["category"],
                    exp["vendor"] or "",
                    _fmt_money(exp["amount"] or 0.0),
                    exp["notes"] or "",
                ]
            )
        flag_table = Table(flag_rows, colWidths=[0.9 * inch, 1.7 * inch, 1.3 * inch, 0.8 * inch, 1.6 * inch])
        flag_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), RED),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(flag_table)

    receipts_missing = [e for e in expenses if not e["receipt_filename"]]
    story.append(Spacer(1, 14))
    story.append(Paragraph("Receipts", section_style))
    story.append(
        Paragraph(
            f"{len(expenses) - len(receipts_missing)} of {len(expenses)} expense(s) have a receipt attached in the system.",
            meta_style,
        )
    )
    if receipts_missing:
        story.append(
            Paragraph(
                "Missing receipts for: "
                + ", ".join(f"{_fmt_date(e['date'])} {e['vendor'] or e['category']}" for e in receipts_missing),
                warn_style,
            )
        )

    receipt_expenses = [e for e in expenses if e["receipt_filename"]]
    if receipt_expenses and upload_dir:
        story.append(PageBreak())
        story.append(Paragraph("Receipt Images", section_style))
        caption_style = ParagraphStyle(
            "ReceiptCaption", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#475569")
        )

        cells = []
        for exp in receipt_expenses:
            filename = exp["receipt_filename"]
            path = Path(upload_dir) / filename
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            caption = f"{_fmt_date(exp['date'])} &mdash; {exp['vendor'] or exp['category']} &mdash; {_fmt_money(exp['amount'] or 0.0)}"
            if not path.exists() or ext not in RECEIPT_IMAGE_EXTENSIONS:
                cells.append([Paragraph(caption, caption_style), Paragraph("<i>(receipt on file, not shown here)</i>", caption_style)])
            else:
                cells.append(_build_receipt_cell(path, caption, caption_style))

        rows = []
        for i in range(0, len(cells), 2):
            row = cells[i:i + 2]
            if len(row) == 1:
                row.append("")
            rows.append(row)

        receipts_table = Table(rows, colWidths=[3.3 * inch, 3.3 * inch])
        receipts_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(receipts_table)

    doc.build(story)
    buffer.seek(0)
    return buffer
