"""Formatting helpers for medical reports: Markdown-ish report text -> HTML blocks and PDF."""

import html
import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PRIMARY = colors.HexColor("#4a86e8")
DARK = colors.HexColor("#343a40")
MUTED = colors.HexColor("#6c757d")
LIGHT_BG = colors.HexColor("#f2f6fd")

_BULLET = re.compile(r"^(\s*)[-*•]\s+(.*)$")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])")


def _inline(text):
    """Escape HTML, then turn **bold** / *italic* into <b>/<i> (valid for both HTML and reportlab)."""
    text = html.escape(text.strip(), quote=False)
    text = _BOLD.sub(r"<b>\1</b>", text)
    return _ITALIC.sub(r"<i>\1</i>", text)


def _plain(text):
    return text.replace("**", "").replace("*", "").strip()


def _heading(text):
    return html.escape(_plain(text).rstrip(":").strip(), quote=False)


# The report's own title and patient details duplicate what the page / PDF header already shows
_SKIPPED_HEADINGS = ("clinical report", "patient information")


def parse_report(text):
    """Split model-written Markdown into blocks for rendering.

    Returns a list of dicts: {"kind": "heading" | "subheading" | "bullet" | "paragraph",
    "html": inline HTML, "level": bullet nesting level (0-based)}. The report title and the
    "Patient Information" section are left out.
    """
    blocks = []
    skipping = False
    for raw in (text or "").splitlines():
        if not raw.strip() or raw.strip() in ("---", "***"):
            continue
        heading = _HEADING.match(raw.strip())
        bullet = _BULLET.match(raw)
        if heading:
            blocks.append({"kind": "heading", "html": _heading(heading.group(1)), "level": 0})
        elif bullet:
            indent = len(bullet.group(1).expandtabs(4))
            level = min(2, (indent + 1) // 3)  # 2 or 4 spaces -> 1, 8 spaces -> 2
            blocks.append({"kind": "bullet", "html": _inline(bullet.group(2)), "level": level})
        elif _plain(raw).endswith(":") and raw.strip().startswith("**"):
            blocks.append({"kind": "subheading", "html": _heading(raw), "level": 0})
        else:
            blocks.append({"kind": "paragraph", "html": _inline(raw), "level": 0})
        if blocks and blocks[-1]["kind"] in ("heading", "subheading"):
            skipping = any(name in blocks[-1]["html"].lower() for name in _SKIPPED_HEADINGS)
            if skipping:
                blocks.pop()
        elif skipping:
            blocks.pop()
    return blocks


def build_report_pdf(report, recording, patient, doctor):
    """Render the detailed clinical report as a styled PDF and return its bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Clinical Report - {patient.name}", author=doctor.full_name if doctor else "",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20, textColor=colors.white,
                                alignment=TA_LEFT, spaceAfter=0, leading=24),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=9.5, textColor=colors.white, leading=13),
        "h1": ParagraphStyle("h1", parent=base["Heading2"], fontSize=13.5, textColor=PRIMARY,
                             spaceBefore=14, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=base["Heading4"], fontSize=10.5, textColor=DARK, spaceBefore=6, spaceAfter=3,
                             keepWithNext=1),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14, textColor=DARK),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8.5, leading=12, textColor=MUTED),
        "label": ParagraphStyle("label", parent=base["Normal"], fontSize=8, leading=10, textColor=MUTED),
        "value": ParagraphStyle("value", parent=base["Normal"], fontSize=10.5, leading=13, textColor=DARK),
    }

    def bullet(text, level=0):
        style = ParagraphStyle(f"bullet{level}", parent=styles["body"], leftIndent=12 + 14 * level,
                               bulletIndent=2 + 14 * level, spaceAfter=2)
        return Paragraph(text, style, bulletText="•" if level == 0 else "–")

    story = []
    generated = (report.created_at or datetime.utcnow()).strftime("%d %B %Y")

    # Banner
    banner = Table(
        [[Paragraph("Clinical Report", styles["title"])],
         [Paragraph(f"MedTranscribe &nbsp;·&nbsp; Generated {generated}", styles["subtitle"])]],
        colWidths=[doc.width],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 12), ("BOTTOMPADDING", (0, -1), (-1, -1), 12),
    ]))
    story += [banner, Spacer(1, 10)]

    # Patient / visit details
    def cell(label, value):
        return [Paragraph(label.upper(), styles["label"]), Paragraph(html.escape(str(value or "-")), styles["value"])]

    duration = f"{recording.duration // 60}:{recording.duration % 60:02d} min" if recording.duration else "-"
    info = Table([
        [cell("Patient", patient.name), cell("Patient ID", patient.patient_id), cell("Age / Sex", f"{patient.age} / {patient.sex}")],
        [cell("Physician", doctor.full_name if doctor else None),
         cell("Visit date", recording.created_at.strftime("%d %B %Y") if recording.created_at else None),
         cell("Recording length", duration)],
    ], colWidths=[doc.width / 3] * 3)
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(info)

    # Clinical report sections (its title and patient block are dropped by parse_report;
    # the banner and details table above already cover them)
    blocks = parse_report(report.full_report)
    if not blocks:
        story.append(Spacer(1, 12))
        story.append(Paragraph("No clinical report has been generated for this consultation yet.", styles["body"]))
    for block in blocks:
        if block["kind"] == "heading":
            story.append(Paragraph(block["html"], styles["h1"]))
        elif block["kind"] == "subheading":
            story.append(Paragraph(block["html"], styles["h2"]))
        elif block["kind"] == "bullet":
            story.append(bullet(block["html"], block["level"]))
        else:
            story.append(Paragraph(block["html"], styles["body"]))

    story += [Spacer(1, 14), Paragraph(
        "This report was generated automatically from a recorded consultation and should be "
        "reviewed by the treating physician.", styles["small"])]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 9 * mm, f"{patient.name} ({patient.patient_id})")
        canvas.drawRightString(A4[0] - doc.rightMargin, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
