"""Azərbaycan əlaqə nömrəsinin yoxlanması və +994 formatına gətirilməsi."""

from __future__ import annotations

import re

MOBILE_PREFIXES = {"10", "50", "51", "55", "60", "70", "77", "99"}


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("994") and len(digits) == 12:
        local = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        local = digits[1:]
    elif len(digits) == 9:
        local = digits
    else:
        raise ValueError("Nömrə tanınmadı.")
    if local[:2] not in MOBILE_PREFIXES or len(local) != 9:
        raise ValueError("Yalnız Azərbaycan mobil nömrəsi qəbul olunur.")
    return f"+994{local}"


def format_local_phone(value: str) -> str:
    """+994501112233 → 050 111 22 33."""
    try:
        normalized = normalize_phone(value)
    except ValueError:
        return (value or "").strip()
    local = normalized[4:]
    return f"0{local[:2]} {local[2:5]} {local[5:7]} {local[7:9]}"


def whatsapp_url(value: str) -> str | None:
    try:
        normalized = normalize_phone(value)
    except ValueError:
        return None
    return f"https://wa.me/{normalized.lstrip('+')}"
