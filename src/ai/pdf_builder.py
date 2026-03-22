"""
Converts tailored resume JSON and cover letter text to PDF files.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


def _make_resume_pdf(resume: dict, output_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "Name", parent=styles["Title"], fontSize=18, spaceAfter=2
    )
    contact_style = ParagraphStyle(
        "Contact", parent=styles["Normal"], fontSize=9, spaceAfter=6, textColor=colors.grey
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor("#2b4a8c"),
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=10, spaceAfter=2
    )
    bullet_style = ParagraphStyle(
        "Bullet", parent=styles["Normal"], fontSize=10, leftIndent=12, spaceAfter=2,
        bulletText="•",
    )

    story = []
    personal = resume.get("personal", {})
    story.append(Paragraph(personal.get("name", ""), name_style))

    contact_parts = [
        personal.get("email", ""),
        personal.get("phone", ""),
        personal.get("linkedin", ""),
        personal.get("github", ""),
    ]
    story.append(Paragraph("  |  ".join(p for p in contact_parts if p), contact_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2b4a8c")))

    if resume.get("summary"):
        story.append(Paragraph("SUMMARY", section_style))
        story.append(Paragraph(resume["summary"], body_style))

    if resume.get("experience"):
        story.append(Paragraph("EXPERIENCE", section_style))
        for exp in resume["experience"]:
            header = f"<b>{exp.get('title', '')}</b> — {exp.get('company', '')}"
            dates = f"{exp.get('start', '')} – {exp.get('end', 'Present')}"
            story.append(Paragraph(f"{header} <font color='grey' size='9'>({dates})</font>", body_style))
            for bullet in exp.get("bullets", []):
                story.append(Paragraph(bullet, bullet_style))
            story.append(Spacer(1, 4))

    if resume.get("education"):
        story.append(Paragraph("EDUCATION", section_style))
        for edu in resume["education"]:
            story.append(Paragraph(
                f"<b>{edu.get('degree', '')}</b> — {edu.get('school', '')} ({edu.get('year', '')})",
                body_style,
            ))

    if resume.get("skills"):
        story.append(Paragraph("SKILLS", section_style))
        story.append(Paragraph(", ".join(resume["skills"]), body_style))

    if resume.get("certifications"):
        story.append(Paragraph("CERTIFICATIONS", section_style))
        for cert in resume["certifications"]:
            story.append(Paragraph(f"• {cert}", body_style))

    doc.build(story)


def _make_cover_letter_pdf(cover_letter_text: str, output_path: Path, name: str = "") -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "CL", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=12
    )
    story = []
    for para in cover_letter_text.split("\n\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(para.replace("\n", " "), body_style))
    if name:
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"Sincerely,<br/>{name}", body_style))
    doc.build(story)


class PDFBuilder:
    def __init__(self, generated_dir: Path) -> None:
        self.generated_dir = generated_dir
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    def build_resume(self, resume: dict, job_key: str) -> Path:
        """Write resume PDF and return its path."""
        out = self.generated_dir / f"resume_{job_key}.pdf"
        _make_resume_pdf(resume, out)
        return out

    def build_cover_letter(
        self, cover_letter_text: str, job_key: str, name: str = ""
    ) -> tuple[Path, Path]:
        """
        Write cover letter PDF and plain text file.
        Returns (pdf_path, txt_path).
        """
        pdf_out = self.generated_dir / f"cover_letter_{job_key}.pdf"
        txt_out = self.generated_dir / f"cover_letter_{job_key}.txt"
        _make_cover_letter_pdf(cover_letter_text, pdf_out, name)
        txt_out.write_text(cover_letter_text, encoding="utf-8")
        return pdf_out, txt_out

    @staticmethod
    def job_key(company: str, title: str) -> str:
        """Sanitized key for file naming."""
        raw = f"{company}_{title}".lower()
        return "".join(c if c.isalnum() or c == "_" else "_" for c in raw)[:60]
