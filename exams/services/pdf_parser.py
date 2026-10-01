"""PDF sınaq fayllarından sual, variant və şəkil çıxarılması."""

from __future__ import annotations

import re
from io import BytesIO
from typing import BinaryIO

from django.core.files.base import ContentFile
from django.db import transaction

QUESTION_START = re.compile(
    r"(?m)^\s*(?:Sual\s+)?(\d{1,3})\s*[\.\)\:]\s+",
    re.IGNORECASE,
)
CHOICE_START = re.compile(
    r"(?m)(?:^|\s)([A-E])\s*[\.\)]",
)
ANSWER_KEY_ITEM = re.compile(
    r"(\d{1,3})\s*[-.:\)]\s*([A-E])",
    re.IGNORECASE,
)
QUESTION_LINE = re.compile(r"^\s*(\d{1,3})\s*[\.\)\:]\s+")
HEADER_LINE = re.compile(
    r"^\s*(BİOLOGİYA|MÜƏLLİM İMTAHANI\s*[–—-].*|AÇIQ TİPLİ TEST TAPŞIRIQLARI|"
    r"Azərbaycan dili|Riyaziyyat|İngilis dili|Rus dili|Həyat bilgisi|Məntiq)\s*$",
    re.IGNORECASE,
)
HEADER_BAND = 72

_SYMBOL_TABLE = str.maketrans(
    {
        "\uf03c": "<",
        "\uf03d": "=",
        "\uf03e": ">",
        "\uf08d": "≥",
        "\uf08c": "≤",
        "\uf0a3": "≤",
        "\uf0b3": "≥",
    }
)

# Times Roman AzLat və oxşar DIM/TQDK şriftləri kiril kodlarla latın Az vizualı saxlayır.
_AZLAT_TABLE = str.maketrans(
    {
        "А": "A",
        "а": "a",
        "Б": "B",
        "б": "b",
        "В": "V",
        "в": "v",
        "Г": "Q",
        "г": "q",
        "Д": "D",
        "д": "d",
        "Е": "E",
        "е": "e",
        "Ж": "C",
        "ж": "c",
        "З": "Z",
        "з": "z",
        "И": "İ",
        "и": "i",
        "Й": "Y",
        "й": "y",
        "К": "K",
        "к": "k",
        "Л": "L",
        "л": "l",
        "М": "M",
        "м": "m",
        "Н": "N",
        "н": "n",
        "О": "O",
        "о": "o",
        "П": "P",
        "п": "p",
        "Р": "R",
        "р": "r",
        "С": "S",
        "с": "s",
        "Т": "T",
        "т": "t",
        "У": "U",
        "у": "u",
        "Ф": "F",
        "ф": "f",
        "Х": "X",
        "х": "x",
        "Ц": "Ü",
        "ц": "ü",
        "Ч": "Ç",
        "ч": "ç",
        "Ш": "Ş",
        "ш": "ş",
        "Щ": "H",
        "щ": "h",
        "Ъ": "J",
        "ъ": "j",
        "Ы": "I",
        "ы": "ı",
        "Ь": "Ğ",
        "ь": "ğ",
        "Э": "G",
        "э": "g",
        "Ю": "Ö",
        "ю": "ö",
        "Я": "Ə",
        "я": "ə",
    }
)


class ParseError(Exception):
    """PDF və ya mətn parse edilə bilmədikdə qaldırılır."""


def decode_azlat(text: str) -> str:
    """AzLat şriftindən çıxan kiril kodları Azərbaycan latınına çevirir."""
    if not text:
        return text
    cyrillic = len(re.findall(r"[А-яЁё]", text))
    if cyrillic == 0:
        return text
    az_latin = len(re.findall(r"[əşğçıüöƏŞĞÇİÜÖ]", text))
    if az_latin > cyrillic:
        return text
    return text.translate(_AZLAT_TABLE)


def _read_bytes(pdf_file: BinaryIO | bytes | str) -> bytes:
    if isinstance(pdf_file, (bytes, bytearray)):
        return bytes(pdf_file)
    if isinstance(pdf_file, str):
        with open(pdf_file, "rb") as handle:
            return handle.read()
    data = pdf_file.read()
    if hasattr(pdf_file, "seek"):
        try:
            pdf_file.seek(0)
        except Exception:
            pass
    if not data:
        raise ParseError("PDF faylı boşdur.")
    return data


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text.strip()


def _normalize_symbols(text: str) -> str:
    return text.translate(_SYMBOL_TABLE)


def _strip_headers(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not HEADER_LINE.match(line))


def _prepare(text: str) -> str:
    return _strip_headers(_normalize_text(_normalize_symbols(decode_azlat(text))))


def _pdfplumber_text(data: bytes) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages.append(_prepare(extracted))
    return "\n".join(pages).strip()


def _clip_text(page, rect) -> str:
    return _prepare(page.get_text("text", clip=rect, sort=True) or "")


def _pymupdf_page_text(page) -> tuple[str, bool]:
    import pymupdf

    mid = page.rect.width / 2
    gutter = 6
    left = _clip_text(
        page, pymupdf.Rect(0, HEADER_BAND, mid - gutter, page.rect.height)
    )
    right = _clip_text(
        page,
        pymupdf.Rect(mid + gutter, HEADER_BAND, page.rect.width, page.rect.height),
    )
    heads = _question_heads(page)
    left_heads = sum(1 for _n, x0, _y0, _y1 in heads if x0 < mid)
    right_heads = sum(1 for _n, x0, _y0, _y1 in heads if x0 >= mid)
    if left_heads and right_heads:
        return f"{left}\n\n{right}", True
    return _clip_text(page, pymupdf.Rect(0, HEADER_BAND, page.rect.width, page.rect.height)), False


def _pymupdf_text(data: bytes) -> tuple[str, bool]:
    import pymupdf

    pages = []
    used_columns = False
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for page in document:
            text, columns = _pymupdf_page_text(page)
            used_columns = used_columns or columns
            pages.append(text)
    return "\n".join(pages).strip(), used_columns


def _question_score(text: str) -> tuple[int, int, int]:
    return len(QUESTION_START.findall(text)), len(CHOICE_START.findall(text)), len(text)


def extract_pdf_text(pdf_file: BinaryIO | bytes | str) -> str:
    """PDF-dən mətn çıxarır: iki sütun, AzLat dekoder, daha zəngin namizəd."""
    data = _read_bytes(pdf_file)
    plumber_text = ""
    fitz_text = ""
    fitz_columns = False
    plumber_error = None
    fitz_error = None

    try:
        plumber_text = _pdfplumber_text(data)
    except Exception as exc:  # noqa: BLE001
        plumber_error = exc

    try:
        fitz_text, fitz_columns = _pymupdf_text(data)
    except Exception as exc:  # noqa: BLE001
        fitz_error = exc

    if fitz_text and fitz_columns:
        return fitz_text

    candidates = [text for text in (fitz_text, plumber_text) if text]
    if not candidates:
        detail = plumber_error or fitz_error
        raise ParseError(f"PDF-dən mətn çıxarıla bilmədi: {detail}")

    return max(candidates, key=_question_score)


def _choice_letter_count(text: str) -> int:
    return len({letter.upper() for letter in CHOICE_START.findall(text or "")})


def _is_real_question_body(body: str) -> bool:
    """Alt bənd (1. 2.) deyil, A–E variantlı həqiqi sualdır."""
    return _choice_letter_count(body) >= 3


def _cut_at_next_question(text: str) -> str:
    for match in QUESTION_START.finditer(text):
        rest = (text[match.end() :] or "").lstrip()
        if _is_real_question_body(rest) or (rest and rest[0].isalpha()):
            return text[: match.start()]
    return text


def _drop_inner_numbered_lists(
    matches: list[re.Match[str]], text: str
) -> list[re.Match[str]]:
    """Match tapşırığındakı '1. 2. 3.' siyahısını yeni sual saymır."""
    kept: list[re.Match[str]] = []
    for index, match in enumerate(matches):
        original = int(match.group(1))
        indent = len(re.match(r"[ \t]*", match.group(0)).group(0))
        last_major = 0
        for prev in reversed(kept):
            prev_n = int(prev.group(1))
            if prev_n >= 10:
                last_major = prev_n
                break
        if original <= 3 and last_major >= 10:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end() : end]
            if not (original == 1 and indent <= 1 and _is_real_question_body(body)):
                continue
        kept.append(match)
    return kept


def parse_questions(text: str) -> list[dict]:
    """Standart sual/variant formatını dictionary siyahısına çevirir.

    Yeni fənn 1-dən yenidən başlayanda əvvəlki suala qatılmır; nömrələr
    unikal qalsın deyə ofsetlə davam edir.
    """
    normalized = _prepare(text)
    matches = _drop_inner_numbered_lists(list(QUESTION_START.finditer(normalized)), normalized)
    if not matches:
        raise ParseError(
            "PDF-də sual tapılmadı. Gözlənilən format: '1.', '1)' və ya 'Sual 1:'."
        )

    real: list[re.Match[str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[match.end() : end]
        if _is_real_question_body(body):
            real.append(match)

    if not real:
        raise ParseError(
            "PDF-də sual tapılmadı. Gözlənilən format: '1.', '1)' və ya 'Sual 1:'."
        )

    questions: list[dict] = []
    offset = 0
    last_original = 0
    for index, match in enumerate(real):
        original = int(match.group(1))
        if last_original and original <= last_original:
            offset = questions[-1]["number"] if questions else 0
        assigned = offset + original
        start = match.end()
        end = real[index + 1].start() if index + 1 < len(real) else len(normalized)
        body = normalized[start:end]
        parsed = _parse_question_body(assigned, body)
        questions.append(parsed)
        last_original = original
    return questions


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


_ROMAN_CHAIN = re.compile(
    r"((?:IV|III|II|I)(?:\s*[><=]\s*(?:IV|III|II|I))+)",
)


def _format_choice_text(value: str) -> str:
    """Cədvəl sütunlarını (A/B müqayisələri) bir sətirdə ayırır."""
    text = _collapse_ws(value)
    parts = _ROMAN_CHAIN.findall(text)
    if len(parts) == 2 and _collapse_ws(" ".join(parts)) == text:
        return f"A: {parts[0]}  |  B: {parts[1]}"
    return text


def _parse_question_body(number: int, body: str) -> dict:
    choice_matches = list(CHOICE_START.finditer(body))
    if not choice_matches:
        return {"number": number, "text": _collapse_ws(body), "choices": []}

    question_text = _collapse_ws(body[: choice_matches[0].start()])
    choices = []
    seen_letters: set[str] = set()
    for index, match in enumerate(choice_matches):
        letter = match.group(1).upper()
        if letter in seen_letters:
            continue
        seen_letters.add(letter)
        start = match.end()
        end = (
            choice_matches[index + 1].start()
            if index + 1 < len(choice_matches)
            else len(body)
        )
        raw = _cut_at_next_question(body[start:end])
        choices.append({"letter": letter, "text": _format_choice_text(raw)})
    return {"number": number, "text": question_text, "choices": choices}


def parse_answer_key(raw: str) -> dict[int, str]:
    """'1-A, 2-C, 3-D' və oxşar formatları {1: 'A', ...} şəklində qaytarır."""
    if not raw or not str(raw).strip():
        return {}
    decoded = decode_azlat(str(raw))
    mapping = {
        int(match.group(1)): match.group(2).upper()
        for match in ANSWER_KEY_ITEM.finditer(decoded)
    }
    if mapping:
        return mapping

    letters = re.findall(r"\b([A-E])\b", decoded, flags=re.IGNORECASE)
    return {index + 1: letter.upper() for index, letter in enumerate(letters)}


def parsed_questions_to_dicts(questions: list[dict], answer_key: str = "") -> list[dict]:
    """Parse nəticəsini JSON-a yaxın, is_correct işarəli struktura gətirir."""
    answers = parse_answer_key(answer_key)
    payload = []
    for item in questions:
        correct_letter = answers.get(item["number"])
        payload.append(
            {
                "number": item["number"],
                "text": item["text"],
                "choices": [
                    {
                        "letter": choice["letter"],
                        "text": choice["text"],
                        "is_correct": correct_letter == choice["letter"],
                    }
                    for choice in item["choices"]
                ],
            }
        )
    return payload


def _question_heads(page) -> list[tuple[int, float, float, float]]:
    """(number, x0, y0, y1) sual başlıqları."""
    heads = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            raw = "".join(span.get("text", "") for span in line.get("spans", []))
            decoded = decode_azlat(raw)
            match = QUESTION_LINE.match(decoded)
            if not match:
                continue
            bbox = line.get("bbox") or [0, 0, 0, 0]
            heads.append((int(match.group(1)), bbox[0], bbox[1], bbox[3]))
    heads.sort(key=lambda item: (item[1] > page.rect.width / 2, item[2]))
    return heads


def _head_has_choices(page, x0: float, y0: float, y1: float) -> bool:
    import pymupdf

    mid = page.rect.width / 2
    left_col = x0 < mid
    col_x0 = 8 if left_col else mid + 4
    col_x1 = mid - 4 if left_col else page.rect.width - 8
    probe = pymupdf.Rect(col_x0, y0, col_x1, min(page.rect.height - 8, y1 + 140))
    snippet = _clip_text(page, probe)
    return _is_real_question_body(snippet)


def collect_question_regions(pdf_file: BinaryIO | bytes | str) -> list[tuple[int, int, object]]:
    """Həqiqi (variantlı) suallar üçün (assigned_number, page_index, rect) qaytarır."""
    import pymupdf

    data = _read_bytes(pdf_file)
    regions: list[tuple[int, int, object]] = []
    offset = 0
    last_original = 0
    last_assigned = 0
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for page_index, page in enumerate(document):
            heads = _question_heads(page)
            accepted: list[tuple[int, float, float, float]] = []
            for head in heads:
                number, x0, y0, y1 = head
                if (
                    accepted
                    and number <= 3
                    and last_original >= 10
                    and abs(x0 - accepted[-1][1]) < 30
                    and 0 < y0 - accepted[-1][2] < 140
                ):
                    continue
                if last_original and number <= last_original:
                    if not _head_has_choices(page, x0, y0, y1):
                        continue
                    offset = last_assigned
                assigned = offset + number
                accepted.append((assigned, x0, y0, y1))
                last_original = number
                last_assigned = assigned
            if not accepted:
                continue
            mid = page.rect.width / 2
            for index, (number, x0, y0, y1) in enumerate(accepted):
                left_col = x0 < mid
                col_x0 = 8 if left_col else mid + 4
                col_x1 = mid - 4 if left_col else page.rect.width - 8
                next_y = page.rect.height - 16
                for _later_n, later_x, later_y, _later_y1 in accepted[index + 1 :]:
                    if (later_x < mid) == left_col:
                        next_y = later_y - 2
                        break
                rect = pymupdf.Rect(col_x0, max(HEADER_BAND, y0 - 2), col_x1, max(y1 + 8, next_y))
                if rect.height < 24 or rect.width < 40:
                    continue
                regions.append((number, page_index, rect))
    return regions


def extract_question_images(pdf_file: BinaryIO | bytes | str) -> dict[int, bytes]:
    """Hər sualın sütun regionunu PNG kimi kəsir (qrafik, şəkil, cədvəl daxil)."""
    import pymupdf

    data = _read_bytes(pdf_file)
    clips: dict[int, bytes] = {}
    regions = collect_question_regions(data)
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for number, page_index, rect in regions:
            if number in clips:
                continue
            pixmap = document[page_index].get_pixmap(
                clip=rect, matrix=pymupdf.Matrix(2, 2), alpha=False
            )
            clips[number] = pixmap.tobytes("png")
    return clips


def extract_choice_images(pdf_file: BinaryIO | bytes | str) -> dict[int, list[bytes]]:
    """Sual regionunda 5 oxşar qrafik varsa, A–E variant şəkilləri kimi kəsir."""
    import pymupdf

    data = _read_bytes(pdf_file)
    result: dict[int, list[bytes]] = {}
    regions = collect_question_regions(data)
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for number, page_index, rect in regions:
            page = document[page_index]
            boxes = []
            for info in page.get_image_info():
                bbox = pymupdf.Rect(info["bbox"])
                if bbox.get_area() < 800 or not rect.intersects(bbox):
                    continue
                # Sual kəsiminin özü deyil, region daxilindəki ayrıca qrafiklər.
                if bbox.width > rect.width * 0.92 and bbox.height > rect.height * 0.7:
                    continue
                boxes.append(bbox)
            if len(boxes) != 5:
                continue
            areas = sorted(box.get_area() for box in boxes)
            median = areas[2]
            if any(area < median / 3 or area > median * 3 for area in areas):
                continue
            boxes.sort(key=lambda box: (round(box.y0 / 10), box.x0))
            pngs = []
            for box in boxes:
                clip = pymupdf.Rect(box).intersect(page.rect)
                clip.x0 = max(rect.x0, clip.x0 - 4)
                clip.y0 = max(rect.y0, clip.y0 - 4)
                clip.x1 = min(rect.x1, clip.x1 + 4)
                clip.y1 = min(rect.y1, clip.y1 + 14)
                pixmap = page.get_pixmap(
                    clip=clip, matrix=pymupdf.Matrix(2, 2), alpha=False
                )
                pngs.append(pixmap.tobytes("png"))
            result[number] = pngs
    return result


@transaction.atomic
def import_exam_from_pdf(exam, pdf_file, answer_key: str = "") -> dict:
    """PDF-i parse edib Exam / Question / Choice modellərinə yazır.

    Düzgün cavab idxal zamanı işarələnmir; onu admin sonradan təyin edir.
    ``answer_key`` saxlanılır, amma tətbiq olunmur.
    """
    del answer_key
    data = _read_bytes(pdf_file)
    text = extract_pdf_text(data)
    parsed = parse_questions(text)
    records = parsed_questions_to_dicts(parsed)
    images = extract_question_images(data)
    choice_images = extract_choice_images(data)

    exam.questions.all().delete()

    marked = 0
    choice_count = 0
    image_count = 0
    from exams.models import Choice, Question

    for item in records:
        question = Question.objects.create(
            exam=exam,
            number=item["number"],
            text=item["text"] or f"Sual {item['number']}",
        )
        png = images.get(item["number"])
        if png:
            question.image.save(
                f"exam{exam.pk}_q{item['number']}.png",
                ContentFile(png),
                save=True,
            )
            image_count += 1
        option_pngs = choice_images.get(item["number"], [])
        for index, choice in enumerate(item["choices"]):
            obj = Choice.objects.create(
                question=question,
                letter=choice["letter"],
                text=choice["text"],
                is_correct=False,
            )
            if index < len(option_pngs):
                obj.image.save(
                    f"exam{exam.pk}_q{item['number']}_{choice['letter']}.png",
                    ContentFile(option_pngs[index]),
                    save=True,
                )
            choice_count += 1

    return {
        "questions": len(records),
        "choices": choice_count,
        "marked_correct": marked,
        "images": image_count,
    }


@transaction.atomic
def apply_answer_key(exam, answer_key: str) -> int:
    """Mövcud suallara cavab açarını tətbiq edir."""
    mapping = parse_answer_key(answer_key)
    if not mapping:
        return 0

    marked = 0
    for question in exam.questions.prefetch_related("choices"):
        letter = mapping.get(question.number)
        for choice in question.choices.all():
            is_correct = letter is not None and choice.letter == letter
            if choice.is_correct != is_correct:
                choice.is_correct = is_correct
                choice.save(update_fields=["is_correct"])
            if is_correct:
                marked += 1
    return marked
