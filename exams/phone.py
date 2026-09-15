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
