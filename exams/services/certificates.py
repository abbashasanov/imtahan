from __future__ import annotations

import secrets
from pathlib import Path

from django.utils import timezone


def generate_certificate_code() -> str:
    year = timezone.now().year
    token = secrets.token_hex(3).upper()
    return f"IMT-{year}-{token}"


def issue_certificate_if_passed(submission):
    from exams.models import Certificate

    if not submission.passed:
        return None
    existing = Certificate.objects.filter(submission=submission).first()
    if existing:
        return existing
    return Certificate.objects.create(
        submission=submission,
        code=generate_certificate_code(),
    )


def _font_path() -> str | None:
    for candidate in (
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\calibri.ttf"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def build_certificate_pdf(certificate) -> bytes:
    import pymupdf

    submission = certificate.submission
    exam = submission.exam
    issued = timezone.localtime(certificate.issued_at).strftime("%d.%m.%Y")

    document = pymupdf.open()
    page = document.new_page(width=842, height=595)
    fontfile = _font_path()
    fontname = "helv"
    if fontfile:
        page.insert_font(fontname="az", fontfile=fontfile)
        fontname = "az"

    page.draw_rect(pymupdf.Rect(24, 24, 818, 571), color=(15 / 255, 110 / 255, 86 / 255), width=3)
    page.draw_rect(pymupdf.Rect(36, 36, 806, 559), color=(228 / 255, 221 / 255, 208 / 255), width=1)

    def text(value, y, size, color=(28 / 255, 36 / 255, 48 / 255)):
        page.insert_textbox(
            pymupdf.Rect(80, y, 762, y + size * 2.2),
            value,
            fontname=fontname,
            fontsize=size,
            color=color,
            align=pymupdf.TEXT_ALIGN_CENTER,
        )

    text("ONLAYN SINAQ İMTAHANI", 70, 13, (91 / 255, 101 / 255, 115 / 255))
    text("SERTİFİKAT", 110, 36, (15 / 255, 110 / 255, 86 / 255))
    text("Bu sənəd təsdiq edir ki,", 175, 14)
    text(certificate.student_name, 210, 28)
    text(f"«{exam.title}» imtahanını uğurla başa vurmuşdur.", 260, 16)
    text(f"Nəticə: {submission.score}%   ·   Keçid balı: {exam.passing_score}%", 310, 15)
    text(f"Tarix: {issued}   ·   Kod: {certificate.code}", 350, 14, (91 / 255, 101 / 255, 115 / 255))
    text("İmtahan platforması", 480, 12, (91 / 255, 101 / 255, 115 / 255))

    data = document.tobytes()
    document.close()
    return data
