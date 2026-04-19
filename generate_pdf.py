"""
generate_pdf.py
---------------
Reads data/fitness_partners.csv and produces a clean PDF formatted as:

    Studio Name
    Owner Name
    Phone Number

Run from the fitness_partners folder:
    python generate_pdf.py
"""

from pathlib import Path
import pandas as pd
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

INPUT_CSV = Path("data/fitness_partners.csv")
OUTPUT_PDF = Path("data/fitness_partners.pdf")


def _clean(value) -> str:
    if pd.isna(value) or str(value).strip().lower() in ("nan", "none", ""):
        return ""
    return str(value).strip()


def build_pdf(csv_path: Path = INPUT_CSV, pdf_path: Path = OUTPUT_PDF) -> Path:
    if not csv_path.exists():
        raise FileNotFoundError(
            f"No data found at {csv_path}.\n"
            "Run 'python main.py' first to collect the studio data."
        )

    df = pd.read_csv(csv_path)
    if df.empty:
        raise ValueError("The CSV is empty — no studios to report.")

    # Sort alphabetically by studio name
    df = df.sort_values("name", ignore_index=True)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=LETTER,
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
        topMargin=1.0 * inch,
        bottomMargin=1.0 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#666666"),
        spaceAfter=18,
    )
    studio_name_style = ParagraphStyle(
        "StudioName",
        parent=styles["Normal"],
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f3460"),
        spaceBefore=14,
        spaceAfter=3,
    )
    owner_style = ParagraphStyle(
        "Owner",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#222222"),
        leftIndent=10,
        spaceAfter=2,
    )
    phone_style = ParagraphStyle(
        "Phone",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#333333"),
        leftIndent=10,
        spaceAfter=2,
    )
    email_style = ParagraphStyle(
        "Email",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#1a6b9a"),
        leftIndent=10,
        spaceAfter=2,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#999999"),
        leftIndent=10,
        spaceAfter=2,
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Nashville Fitness Partnership Targets", title_style))
    story.append(Paragraph(
        f"{len(df)} studios identified  |  Potential IV therapy partnership prospects",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a2e")))

    # ── Studio Entries ────────────────────────────────────────────────────────
    for _, row in df.iterrows():
        name = _clean(row.get("name", "")) or "Unknown Studio"
        owner = _clean(row.get("owner_names", "")) or "Owner not found"
        phone = _clean(row.get("phone", "")) or "Phone not listed"
        email = _clean(row.get("email", ""))
        address = _clean(row.get("address", ""))
        category = _clean(row.get("category", ""))
        website = _clean(row.get("website", ""))
        rating = _clean(row.get("rating", ""))

        # Primary lines
        story.append(Paragraph(name, studio_name_style))
        story.append(Paragraph(f"Owner: {owner}", owner_style))
        story.append(Paragraph(f"Phone: {phone}", phone_style))
        if email:
            story.append(Paragraph(f"Email: {email}", email_style))

        # Supporting info in smaller gray text
        if address:
            story.append(Paragraph(f"Address: {address}", meta_style))
        if category:
            story.append(Paragraph(f"Type: {category}", meta_style))
        if website:
            story.append(Paragraph(f"Website: {website}", meta_style))
        if rating:
            story.append(Paragraph(f"Google Rating: {rating} ★", meta_style))

        story.append(HRFlowable(
            width="100%", thickness=0.4,
            color=colors.HexColor("#dddddd"),
            spaceAfter=2,
        ))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Data sourced from Google Maps and TN Secretary of State public registry. "
        "Owner information reflects public filings — verify before outreach.",
        ParagraphStyle(
            "Footer", parent=styles["Normal"],
            fontSize=7, textColor=colors.HexColor("#bbbbbb"),
        ),
    ))

    doc.build(story)
    return pdf_path


if __name__ == "__main__":
    try:
        out = build_pdf()
        print(f"PDF saved to: {out}")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")