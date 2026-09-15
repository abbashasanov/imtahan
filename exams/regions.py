"""Azərbaycanın şəhər və rayonları — faktiki yaşayış yeri seçimi."""

BAKU = "Bakı"

BAKU_DISTRICTS = (
    "Binəqədi",
    "Xətai",
    "Xəzər",
    "Nərimanov",
    "Nəsimi",
    "Nizami",
    "Pirallahı",
    "Qaradağ",
    "Sabunçu",
    "Səbail",
    "Suraxanı",
    "Yasamal",
)

CITIES = (
    "Gəncə",
    "Sumqayıt",
    "Mingəçevir",
    "Naftalan",
    "Naxçıvan",
    "Şəki",
    "Şirvan",
    "Yevlax",
)

RAYONS = (
    "Abşeron",
    "Ağcabədi",
    "Ağdam",
    "Ağdaş",
    "Ağstafa",
    "Ağsu",
    "Astara",
    "Babək",
    "Balakən",
    "Beyləqan",
    "Bərdə",
    "Biləsuvar",
    "Cəbrayıl",
    "Cəlilabad",
    "Culfa",
    "Daşkəsən",
    "Füzuli",
    "Gədəbəy",
    "Goranboy",
    "Göyçay",
    "Göygöl",
    "Hacıqabul",
    "Xaçmaz",
    "Xızı",
    "Xocalı",
    "Xocavənd",
    "İmişli",
    "İsmayıllı",
    "Kəlbəcər",
    "Kəngərli",
    "Kürdəmir",
    "Laçın",
    "Lerik",
    "Lənkəran",
    "Masallı",
    "Neftçala",
    "Oğuz",
    "Ordubad",
    "Qax",
    "Qazax",
    "Qəbələ",
    "Qobustan",
    "Quba",
    "Qubadlı",
    "Qusar",
    "Saatlı",
    "Sabirabad",
    "Salyan",
    "Samux",
    "Siyəzən",
    "Sədərək",
    "Şabran",
    "Şahbuz",
    "Şamaxı",
    "Şəmkir",
    "Şərur",
    "Şuşa",
    "Tərtər",
    "Tovuz",
    "Ucar",
    "Yardımlı",
    "Zaqatala",
    "Zəngilan",
    "Zərdab",
)

REGION_GROUPS = (
    ("Şəhərlər", (BAKU,) + CITIES),
    ("Rayonlar", RAYONS),
)

REGION_CHOICES = tuple((name, name) for _label, names in REGION_GROUPS for name in names)
REGION_VALUES = {value for value, _label in REGION_CHOICES}

BAKU_DISTRICT_CHOICES = tuple((name, name) for name in BAKU_DISTRICTS)
BAKU_DISTRICT_VALUES = set(BAKU_DISTRICTS)

_GRADE_SUFFIX = {
    1: "ci",
    2: "ci",
    3: "cü",
    4: "cü",
    5: "ci",
    6: "cı",
    7: "ci",
    8: "ci",
    9: "cu",
    10: "cu",
    11: "ci",
}


def grade_label(number) -> str:
    if not number:
        return ""
    number = int(number)
    return f"{number}-{_GRADE_SUFFIX.get(number, 'ci')} sinif"


GRADE_CHOICES = tuple((number, grade_label(number)) for number in range(1, 12))

DEFAULT_SUBJECTS = (
    "Azərbaycan dili",
    "Riyaziyyat",
    "İngilis dili",
    "Rus dili",
    "Həyat bilgisi",
    "Məntiq",
)


def parse_legacy_district(value: str) -> tuple[str, str]:
    """Köhnə 'Bakı — Yasamal' və ya 'Gəncə' dəyərini (region, baku_district) edir."""
    raw = (value or "").strip()
    if raw.startswith("Bakı — "):
        district = raw.removeprefix("Bakı — ").strip()
        return BAKU, district
    if raw.startswith("Bakı - "):
        district = raw.removeprefix("Bakı - ").strip()
        return BAKU, district
    return raw, ""
