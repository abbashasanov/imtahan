from datetime import timedelta
from pathlib import Path
import unittest

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from exams.models import Choice, Exam, ExamSubmission, Question, SiteSettings, StudentProfile, Subject
from exams.services.pdf_parser import (
    ParseError,
    apply_answer_key,
    collect_question_regions,
    decode_azlat,
    extract_pdf_text,
    import_exam_from_pdf,
    parse_answer_key,
    parse_questions,
    parsed_questions_to_dicts,
)

SAMPLE_TEXT = """
Sınaq imtahanı

1. Azərbaycanın paytaxtı hansı şəhərdir?
A) Gəncə
B) Bakı
C) Sumqayıt
D) Şəki
E) Naxçıvan

2. 2 + 2 neçədir?
A) 3
B) 4
C) 5
D) 6
E) 8

Sual 3: HTML nədir?
A) Proqramlaşdırma dili
B) İşləmə sistemi
C) İşarələmə dili
D) Verilənlər bazası
E) Brauzer
"""


def make_pdf(text: str) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def make_top_right_question_pdf() -> bytes:
    """Sağ sütunda y=61-də başlayan sual HEADER_BAND kəsiminə düşməməlidir."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((40, 90), "1. Sol sual hansidir?", fontsize=11)
    page.insert_text((50, 120), "A) a", fontsize=11)
    page.insert_text((50, 140), "B) b", fontsize=11)
    page.insert_text((50, 160), "C) c", fontsize=11)
    page.insert_text((50, 180), "D) d", fontsize=11)
    page.insert_text((320, 61), "7. Sag sual hansidir?", fontsize=11)
    page.insert_text((330, 90), "A) x", fontsize=11)
    page.insert_text((330, 110), "B) y", fontsize=11)
    page.insert_text((330, 130), "C) z", fontsize=11)
    page.insert_text((330, 150), "D) w", fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def make_scrambled_twocolumn_pdf() -> bytes:
    """İki sütun + 2x2 variant toru; PDF-də əvvəl aşağıdakı sual çəkilir."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=596, height=842)
    page.insert_text((320, 400), "4. Natiq cox temiz oglandir.", fontsize=11)
    page.insert_text((330, 430), "A) -ci", fontsize=11)
    page.insert_text((330, 460), "C) -kar", fontsize=11)
    page.insert_text((460, 430), "B) -in", fontsize=11)
    page.insert_text((460, 460), "D) -ler", fontsize=11)
    page.insert_text((32, 140), "1. Birinci sual hansidir?", fontsize=11)
    page.insert_text((44, 170), "A) bir-a", fontsize=11)
    page.insert_text((44, 200), "C) bir-c", fontsize=11)
    page.insert_text((177, 170), "B) bir-b", fontsize=11)
    page.insert_text((177, 200), "D) bir-d", fontsize=11)
    page.insert_text((32, 280), "2. Ikinci sual hansidir?", fontsize=11)
    page.insert_text((44, 310), "A) iki-a", fontsize=11)
    page.insert_text((44, 340), "B) iki-b", fontsize=11)
    page.insert_text((44, 370), "C) iki-c", fontsize=11)
    page.insert_text((44, 400), "D) iki-d", fontsize=11)
    page.insert_text((320, 140), "3. Ucuncu sual hansidir?", fontsize=11)
    page.insert_text((330, 170), "A) uc-a", fontsize=11)
    page.insert_text((330, 200), "B) uc-b", fontsize=11)
    page.insert_text((330, 230), "C) uc-c", fontsize=11)
    page.insert_text((330, 260), "D) uc-d", fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def make_grade1_image_gap_pdf() -> bytes:
    """1-ci sinif: sağda 44/45, növbəti səhifədə 47/49 və 48/50 şəkil-tipli başlıqlar."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=596, height=842)
    page.insert_text((32, 130), "43. Hansı şəkil fərqlidir?", fontsize=11)
    page.insert_text((44, 160), "A) a", fontsize=11)
    page.insert_text((44, 180), "B) b", fontsize=11)
    page.insert_text((44, 200), "C) c", fontsize=11)
    page.insert_text((44, 220), "D) d", fontsize=11)
    page.insert_text((320, 130), "44. ANA = ATA = ?", fontsize=11)
    page.insert_text((330, 160), "A)", fontsize=11)
    page.insert_text((430, 160), "B)", fontsize=11)
    page.insert_text((330, 190), "C)", fontsize=11)
    page.insert_text((430, 190), "D)", fontsize=11)
    page.insert_text((320, 330), "45.", fontsize=11)
    page.insert_text((330, 360), "A)", fontsize=11)
    page.insert_text((430, 360), "B)", fontsize=11)
    page.insert_text((330, 390), "C)", fontsize=11)
    page.insert_text((430, 390), "D)", fontsize=11)
    page.insert_text((320, 520), "46. Aysel menim xalamdir?", fontsize=11)
    page.insert_text((330, 550), "A) nene", fontsize=11)
    page.insert_text((330, 570), "B) ana", fontsize=11)
    page.insert_text((330, 590), "C) bibi", fontsize=11)
    page.insert_text((330, 610), "D) xala", fontsize=11)

    page2 = document.new_page(width=596, height=842)
    page2.insert_text((32, 130), "47.", fontsize=11)
    page2.insert_text((44, 160), "A)", fontsize=11)
    page2.insert_text((144, 160), "B)", fontsize=11)
    page2.insert_text((44, 190), "C)", fontsize=11)
    page2.insert_text((144, 190), "D)", fontsize=11)
    page2.insert_text((32, 400), "48. Sozler arasinda elaqe?", fontsize=11)
    page2.insert_text((44, 430), "A)", fontsize=11)
    page2.insert_text((144, 430), "B)", fontsize=11)
    page2.insert_text((44, 460), "C)", fontsize=11)
    page2.insert_text((144, 460), "D)", fontsize=11)
    page2.insert_text((320, 130), "49.", fontsize=11)
    page2.insert_text((330, 160), "A)", fontsize=11)
    page2.insert_text((430, 160), "B)", fontsize=11)
    page2.insert_text((330, 190), "C)", fontsize=11)
    page2.insert_text((430, 190), "D)", fontsize=11)
    page2.insert_text((320, 400), "50.", fontsize=11)
    page2.insert_text((330, 430), "A) 6", fontsize=11)
    page2.insert_text((430, 430), "B) 8", fontsize=11)
    page2.insert_text((330, 460), "C) 9", fontsize=11)
    page2.insert_text((430, 460), "D) 10", fontsize=11)
    data = document.tobytes()
    document.close()
    return data


class QuestionParseTests(TestCase):
    def test_parses_numbered_and_sual_prefix_formats(self):
        questions = parse_questions(SAMPLE_TEXT)
        self.assertEqual([item["number"] for item in questions], [1, 2, 3])
        self.assertEqual(questions[0]["text"], "Azərbaycanın paytaxtı hansı şəhərdir?")
        self.assertEqual([c["letter"] for c in questions[0]["choices"]], list("ABCDE"))
        self.assertEqual(questions[0]["choices"][1]["text"], "Bakı")
        self.assertEqual(questions[2]["text"], "HTML nədir?")

    def test_parenthesis_question_numbers(self):
        text = "1) Birinci sual\nA) bir\nB) iki\nC) üç\nD) dörd\nE) beş\n"
        questions = parse_questions(text)
        self.assertEqual(questions[0]["number"], 1)
        self.assertEqual(len(questions[0]["choices"]), 5)

    def test_inline_choices_on_one_line(self):
        text = (
            "5. Nisbəti tapın:\n"
            "A) 1 : 4 B) 1 : 5 C) 2 : 11 D) 2 : 9 E) 1 : 6\n"
        )
        questions = parse_questions(text)
        self.assertEqual([c["letter"] for c in questions[0]["choices"]], list("ABCDE"))
        self.assertEqual(questions[0]["choices"][0]["text"], "1 : 4")
        self.assertEqual(questions[0]["choices"][4]["text"], "1 : 6")

    def test_azlat_cyrillic_font_decoding(self):
        self.assertEqual(decode_azlat("МЦЯЛЛИМ ИМТАЩАНЫ"), "MÜƏLLİM İMTAHANI")
        self.assertEqual(decode_azlat("Ганында"), "Qanında")
        text = (
            "4. Fotosintezin işıq mərhələsində hansına ehtiyac duyulmur?\n"
            "A) Elektron daşınmasına\n"
            "Б) Ишыг енеръисиня\n"
            "Ж) Хлорофил пигментиня\n"
            "Д) НАДП+\n"
            "Е) Карбон газына\n"
        )
        questions = parse_questions(text)
        self.assertEqual([c["letter"] for c in questions[0]["choices"]], list("ABCDE"))
        self.assertIn("enerjisinə", questions[0]["choices"][1]["text"])
        self.assertIn("Xlorofil", questions[0]["choices"][2]["text"])

    def test_symbol_font_greater_than_and_no_subitem_split(self):
        text = (
            "6. Şəkilə əsasən seçin:\n"
            "A) I \uf03e II \uf03e III\n"
            "B) III \uf03e I\n"
            "C) III = I\n"
            "D) II \uf03e I\n"
            "E) I \uf03e II\n"
            "1. Alt bənddir\n"
            "7. Növbəti sual\n"
            "A) bir\nB) iki\nC) üç\nD) dörd\nE) beş\n"
        )
        questions = parse_questions(text)
        self.assertEqual([item["number"] for item in questions], [6, 7])
        self.assertIn(">", questions[0]["choices"][0]["text"])
        self.assertNotIn("Alt bənddir", questions[1]["text"])

        table = (
            "6. Şəkilə əsasən seçin:\n"
            "A) I \uf03e II \uf03e III III \uf03e II \uf03e I\n"
            "B) III \uf03e I\n"
            "C) III = I\n"
            "D) II \uf03e I\n"
            "E) I \uf03e II\n"
        )
        formatted = parse_questions(table)
        self.assertEqual(
            formatted[0]["choices"][0]["text"],
            "A: I > II > III  |  B: III > II > I",
        )

    def test_missing_questions_raise(self):
        with self.assertRaises(ParseError):
            parse_questions("Heç bir sual yoxdur.")

    def test_new_section_restart_does_not_swallow_questions(self):
        text = """
4. Verilmiş cümlədə simvolun yerinə hansı şəkilçi yazıla bilər?
A) -çı
B) -çi
C) -çu
D) -cə
E) -ca

1. "?" işarəsinin yerinə uyğun gəlməyən söz hansıdır?
A) k...manda
B) k...nsert
C) k...randaş
D) k...lbasa
E) k...smonavt

2. Hansı cümlədə bütün sözlər düzgün yazılıb?
A) Təbiyyət
B) Palıd
C) Kitab
D) Qədim
E) Karvan

5. Hansı cümlədə 3 söz səhv yazılıb?
A) bir
B) iki
C) üç
D) dörd
E) beş
"""
        questions = parse_questions(text)
        numbers = [item["number"] for item in questions]
        self.assertEqual(numbers, [4, 5, 6, 9])
        q4 = next(item for item in questions if item["number"] == 4)
        self.assertEqual(q4["text"], "Verilmiş cümlədə simvolun yerinə hansı şəkilçi yazıla bilər?")
        self.assertEqual(q4["choices"][-1]["text"], "-ca")
        self.assertFalse(any("Hansı cümlədə" in choice["text"] for choice in q4["choices"]))
        q5 = next(item for item in questions if item["number"] == 5)
        self.assertIn("işarəsinin yerinə", q5["text"])
        self.assertEqual(q5["choices"][3]["text"], "k...lbasa")
        q6 = next(item for item in questions if item["number"] == 6)
        self.assertIn("bütün sözlər düzgün", q6["text"])
        q9 = next(item for item in questions if item["number"] == 9)
        self.assertIn("3 söz səhv", q9["text"])

    def test_spaced_empty_choices_still_count_as_question(self):
        text = (
            "8. Verilmiş sözlərdən neçəsi dörd cür yazılan şəkilçi qəbul etmişdir?\n"
            "  A)                  B)\n"
            "  C)                 D)\n"
            "9. Növbəti sual\n"
            "A) bir\nB) iki\nC) üç\nD) dörd\n"
        )
        questions = parse_questions(text)
        self.assertEqual([item["number"] for item in questions], [8, 9])
        self.assertEqual([choice["letter"] for choice in questions[0]["choices"]], list("ABCD"))
        self.assertIn("dörd cür", questions[0]["text"])

    def test_indented_match_list_is_not_a_new_question(self):
        text = (
            "60. Match. Uyğunlaşdırın.\n"
            "    1. What’s your name?\n"
            "    2. What’s your favourite day?\n"
            "    3. How do you spell your name?\n"
            "A) 1-a\nB) 1-b\nC) 1-c\nD) 1-d\n"
        )
        questions = parse_questions(text)
        self.assertEqual([item["number"] for item in questions], [60])
        self.assertIn("Match", questions[0]["text"])
        self.assertEqual(len(questions[0]["choices"]), 4)

        unindented = (
            "59. Digərlərindən fərqli olanı seçin.\n"
            "A) peas\nB) apple\nC) orange\nD) fries\n"
            "60. Match.\n"
            "1. What’s your name?\n"
            "2. What’s your favourite day?\n"
            "3. How do you spell your name?\n"
            "A) 1-a\nB) 1-b\nC) 1-c\nD) 1-d\n"
        )
        questions = parse_questions(unindented)
        self.assertEqual([item["number"] for item in questions], [59, 60])
        self.assertIn("Match", questions[1]["text"])

    def test_twocolumn_pdf_uses_visual_order_not_draw_order(self):
        questions = parse_questions(extract_pdf_text(make_scrambled_twocolumn_pdf()))
        self.assertEqual([item["number"] for item in questions], [1, 2, 3, 4])
        first = questions[0]
        self.assertIn("Birinci sual", first["text"])
        self.assertEqual([choice["letter"] for choice in first["choices"]], list("ABCD"))
        self.assertEqual([choice["text"] for choice in first["choices"]], ["bir-a", "bir-b", "bir-c", "bir-d"])
        self.assertFalse(any("Natiq" in choice["text"] for choice in first["choices"]))
        self.assertIn("Ikinci sual", questions[1]["text"])
        self.assertIn("Ucuncu sual", questions[2]["text"])
        fourth = questions[3]
        self.assertIn("Natiq", fourth["text"])
        self.assertEqual(fourth["choices"][0]["text"], "-ci")
        self.assertEqual(fourth["choices"][1]["text"], "-in")

    def test_zero_width_after_question_number_is_still_parsed(self):
        text = (
            "24. 5 onluq 4 təklik?\n"
            "A) 75\nB) 64\nC) 54\nD) 45\n"
            "25.\u200c \u200c Fikrimdə tutduğum ədədin onluğu 6-dır.\n"
            "A)\u200c 66\nB)\u200c 63\nC)\u200c 48\nD)\u200c 54\n"
            "31.\u200c  \u200cMəktəb daxilində şagirdlər hansı qaydaya əməl etməlidirlər?\n"
            "A)\u200c Qəza siqnalına toxunmamaq.\n"
            "B)\u200c Dərsə gecikmək.\n"
            "C)\u200c Bitkilərə ziyan vurmaq.\n"
            "D) Sinif yoldaşları ilə danışmaq.\n"
            "46.\u200c\n"
            "A) 11\nB) 13\nC) 9\nD) 10\n"
        )
        questions = parse_questions(text)
        self.assertEqual([item["number"] for item in questions], [24, 25, 31, 46])
        self.assertIn("Fikrimdə", questions[1]["text"])
        self.assertEqual(questions[1]["choices"][0]["text"], "66")
        self.assertIn("Məktəb daxilində", questions[2]["text"])
        self.assertEqual([choice["letter"] for choice in questions[3]["choices"]], list("ABCD"))

    def test_image_only_consecutive_questions_are_not_merged(self):
        text = (
            "43. Hansı şəkil fərqlidir?\n"
            "A) \nB) \nC) \nD) \n"
            "44. A N A = A T A = ?\n"
            "A) \nB) \nC) \nD) \n"
            "45.\u200c\n"
            "?\n"
            "46. Aysel mənim xalamdır. Onun anası mənim nəyimdir?\n"
            "A) nənəm\nB) anam\nC) bibim\nD) xalam\n"
            "47.\u200c\n"
            "+ = ?\n"
            "48. Sözlər arasında əlaqəyə əsasən məntiqi tapın.\n"
            "A) \nB) \nC) \nD) \n"
            "49.\u200c\n"
            "?\n"
            "50.\u200c\n"
            "+ + 2 6 ?\n"
            "A) 6\nB) 8\nC) 9\nD) 10\n"
        )
        questions = parse_questions(text)
        numbers = [item["number"] for item in questions]
        self.assertEqual(numbers, [43, 44, 45, 46, 47, 48, 49, 50])
        q44 = next(item for item in questions if item["number"] == 44)
        q45 = next(item for item in questions if item["number"] == 45)
        q47 = next(item for item in questions if item["number"] == 47)
        q48 = next(item for item in questions if item["number"] == 48)
        q49 = next(item for item in questions if item["number"] == 49)
        q50 = next(item for item in questions if item["number"] == 50)
        self.assertIn("A N A", q44["text"])
        self.assertNotIn("45.", q44["text"])
        self.assertEqual([choice["letter"] for choice in q45["choices"]], list("ABCD"))
        self.assertEqual([choice["letter"] for choice in q47["choices"]], list("ABCD"))
        self.assertNotIn("49.", q47["text"])
        self.assertIn("Sözlər arasında", q48["text"])
        self.assertNotIn("50.", q48["text"])
        self.assertEqual([choice["letter"] for choice in q49["choices"]], list("ABCD"))
        self.assertEqual(q50["choices"][0]["text"], "6")

    def test_grade1_image_gap_regions_are_split(self):
        pdf = make_grade1_image_gap_pdf()
        questions = parse_questions(extract_pdf_text(pdf))
        self.assertEqual(
            [item["number"] for item in questions],
            [43, 44, 45, 46, 47, 48, 49, 50],
        )
        regions = {number: rect for number, _page, rect in collect_question_regions(pdf)}
        for number in (44, 45, 47, 49, 50):
            self.assertIn(number, regions)
        self.assertLessEqual(regions[44].y1, regions[45].y0 + 4)
        self.assertLessEqual(regions[47].y1, regions[48].y0 + 4)
        self.assertLessEqual(regions[49].y1, regions[50].y0 + 4)

    def test_low_header_question_is_not_clipped(self):
        questions = parse_questions(extract_pdf_text(make_top_right_question_pdf()))
        numbers = [item["number"] for item in questions]
        self.assertIn(1, numbers)
        self.assertIn(7, numbers)
        sag = next(item for item in questions if item["number"] == 7)
        self.assertIn("Sag sual", sag["text"])
        self.assertEqual([choice["letter"] for choice in sag["choices"]], list("ABCD"))

    def test_overlapping_section_numbers_continue_sequentially(self):
        text = (
            "50. Choose the INCORRECT sentence.\n"
            "A) one\nB) two\nC) three\nD) four\n"
            "41. Glasnye bukvy\n"
            "A) e\nB) b\nC) o\nD) u\n"
            "42. Slova\n"
            "A) volk\nB) leto\nC) dom\nD) kot\n"
        )
        questions = parse_questions(text)
        self.assertEqual([item["number"] for item in questions], [50, 51, 52])
        self.assertIn("Glasnye", questions[1]["text"])
        self.assertIn("Slova", questions[2]["text"])

    def test_stray_column_letter_does_not_eat_choice_a(self):
        text = (
            "7. Hansı sözdə sait səs uzanır?\n"
            "SİNA) çovğun\n"
            "B) zavod\n"
            "C) lövbər\n"
            "D) qanun\n"
        )
        questions = parse_questions(text)
        self.assertEqual([choice["letter"] for choice in questions[0]["choices"]], list("ABCD"))
        self.assertEqual(questions[0]["choices"][0]["text"], "çovğun")
        self.assertNotIn("SİNA)", questions[0]["text"])

    def test_passage_instruction_is_not_left_in_previous_choice(self):
        text = (
            "11. Hansı sözdə k fərqlidir?\n"
            "A) hakim\nB) çiçək\nC) kirpi\nD) körpü\n"
            "Mətnə əsasən 12 15 nömrəli tapşırıqları yerinə yetirin. Yerdən Günəşə qədər.\n"
            "12. Mətndə hansı suala cavab yoxdur?\n"
            "A) bir\nB) iki\nC) üç\nD) dörd\n"
        )
        questions = parse_questions(text)
        self.assertEqual([item["number"] for item in questions], [11, 12])
        self.assertFalse(any("Mətnə" in choice["text"] for choice in questions[0]["choices"]))
        self.assertFalse(any("Günəşə" in choice["text"] for choice in questions[0]["choices"]))
        self.assertIn("Mətnə əsasən", questions[1]["text"])
        self.assertIn("Günəşə", questions[1]["text"])

    def test_header_fragment_is_stripped_from_choice(self):
        text = (
            "3. Hansı bənd doğru deyil?\n"
            "A) vətən\nB) ətir\nC) bulud\nD) günəş can dili\n"
            "4. Növbəti sual\n"
            "A) bir\nB) iki\nC) üç\nD) dörd iyyat\n"
        )
        questions = parse_questions(text)
        self.assertEqual(questions[0]["choices"][3]["text"], "günəş")
        self.assertEqual(questions[1]["choices"][3]["text"], "dörd")


class AnswerKeyTests(TestCase):
    def test_comma_separated_key(self):
        self.assertEqual(
            parse_answer_key("1-A, 2-C, 3-D"),
            {1: "A", 2: "C", 3: "D"},
        )

    def test_positional_fallback(self):
        self.assertEqual(parse_answer_key("B, D, E"), {1: "B", 2: "D", 3: "E"})

    def test_marks_correct_choices_in_payload(self):
        payload = parsed_questions_to_dicts(parse_questions(SAMPLE_TEXT), "1-B, 2-B, 3-C")
        self.assertTrue(payload[0]["choices"][1]["is_correct"])
        self.assertFalse(payload[0]["choices"][0]["is_correct"])
        self.assertTrue(payload[2]["choices"][2]["is_correct"])


class ImportExamTests(TestCase):
    def test_import_from_pdf_does_not_mark_correct_answers(self):
        exam = Exam.objects.create(title="Riyaziyyat sınağı", duration_minutes=45)
        pdf_bytes = make_pdf(SAMPLE_TEXT)
        upload = SimpleUploadedFile("sinay.pdf", pdf_bytes, content_type="application/pdf")

        result = import_exam_from_pdf(exam, upload, answer_key="1-B, 2-B, 3-C")

        self.assertEqual(result["questions"], 3)
        self.assertEqual(result["marked_correct"], 0)
        self.assertEqual(Question.objects.filter(exam=exam).count(), 3)
        self.assertEqual(Choice.objects.filter(question__exam=exam, is_correct=True).count(), 0)

    def test_apply_answer_key_later(self):
        exam = Exam.objects.create(title="Tarix")
        upload = SimpleUploadedFile(
            "tarix.pdf",
            make_pdf(SAMPLE_TEXT),
            content_type="application/pdf",
        )
        import_exam_from_pdf(exam, upload)
        self.assertEqual(Choice.objects.filter(question__exam=exam, is_correct=True).count(), 0)

        marked = apply_answer_key(exam, "1-B, 2-B, 3-C")
        self.assertEqual(marked, 3)
        self.assertTrue(
            Choice.objects.get(question__exam=exam, question__number=1, letter="B").is_correct
        )

    def test_reimport_replaces_old_questions(self):
        exam = Exam.objects.create(title="Kimya")
        first = SimpleUploadedFile("a.pdf", make_pdf(SAMPLE_TEXT), content_type="application/pdf")
        import_exam_from_pdf(exam, first)
        second_text = "1. Yeni sual?\nA) x\nB) y\nC) z\nD) w\nE) q\n"
        second = SimpleUploadedFile(
            "b.pdf",
            make_pdf(second_text),
            content_type="application/pdf",
        )
        import_exam_from_pdf(exam, second, answer_key="1-A")
        self.assertEqual(Question.objects.filter(exam=exam).count(), 1)
        self.assertEqual(Question.objects.get(exam=exam).text, "Yeni sual?")
        self.assertEqual(Choice.objects.filter(question__exam=exam, is_correct=True).count(), 0)

    def test_manual_question_can_be_added_after_pdf_import(self):
        exam = Exam.objects.create(title="PDF sonra əl")
        upload = SimpleUploadedFile("a.pdf", make_pdf(SAMPLE_TEXT), content_type="application/pdf")
        import_exam_from_pdf(exam, upload)
        self.assertEqual(Question.objects.filter(exam=exam).count(), 3)

        admin = get_user_model().objects.create_superuser("adminpdf", "ap@test.local", "adminpass")
        client = self.client
        client.force_login(admin)
        response = client.post(
            f"/panel/exams/{exam.pk}/questions/new/",
            {
                "number": "4",
                "text": "PDF-dən sonra əl ilə",
                "choices-TOTAL_FORMS": "5",
                "choices-INITIAL_FORMS": "0",
                "choices-MIN_NUM_FORMS": "0",
                "choices-MAX_NUM_FORMS": "5",
                "choices-0-letter": "A",
                "choices-0-text": "bir",
                "choices-1-letter": "B",
                "choices-1-text": "iki",
            },
        )
        self.assertRedirects(response, f"/panel/exams/{exam.pk}/#suallar")
        self.assertEqual(Question.objects.filter(exam=exam).count(), 4)
        extra = Question.objects.get(exam=exam, number=4)
        self.assertEqual(extra.text, "PDF-dən sonra əl ilə")
        self.assertTrue(Question.objects.filter(exam=exam, number=1).exists())


class MediaUrlTests(TestCase):
    def test_media_url_is_root_absolute(self):
        from django.conf import settings

        self.assertTrue(settings.MEDIA_URL.startswith("/"))
        self.assertTrue(settings.STATIC_URL.startswith("/"))

    def test_question_image_src_is_not_relative_to_exam_path(self):
        from django.core.files.base import ContentFile

        user = complete_student("sekilci")
        exam = Exam.objects.create(title="Şəkilli", duration_minutes=10, is_active=True)
        question = Question.objects.create(exam=exam, number=1, text="Şəkil sualı")
        Choice.objects.create(question=question, letter="A", text="a", is_correct=True)
        question.image.save("q1.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)
        self.client.force_login(user)
        response = self.client.get(f"/exams/{exam.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'src="{question.image.url}"')
        self.assertTrue(question.image.url.startswith("/media/"))
        self.assertNotContains(response, f"/exams/{exam.pk}/media/")


def complete_student(
    username,
    phone="+994501112233",
    region="Bakı",
    baku_district="Yasamal",
    address="",
    grade=5,
    first_name="Ayan",
    last_name="Test",
):
    user = get_user_model().objects.create_user(
        username=username,
        password="test12345",
        first_name=first_name,
        last_name=last_name,
    )
    StudentProfile.objects.create(
        user=user,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        grade=grade,
        region=region,
        baku_district=baku_district,
        address=address,
    )
    return user


class StudentExamFlowTests(TestCase):
    def setUp(self):
        self.user = complete_student("telebe")
        self.exam = Exam.objects.create(title="Coğrafiya", duration_minutes=10, is_active=True)
        question = Question.objects.create(exam=self.exam, number=1, text="Paytaxt?")
        self.correct = Choice.objects.create(question=question, letter="B", text="Bakı", is_correct=True)
        Choice.objects.create(question=question, letter="A", text="Gəncə", is_correct=False)

    def test_submit_exam_computes_score(self):
        self.client.force_login(self.user)
        response = self.client.post(
            f"/exams/{self.exam.pk}/",
            {f"q_{self.exam.questions.first().pk}": str(self.correct.pk)},
        )
        self.assertEqual(response.status_code, 302)
        submission = self.user.exam_submissions.get(exam=self.exam)
        self.assertTrue(submission.is_completed)
        self.assertEqual(float(submission.score), 100.0)
        self.assertTrue(hasattr(submission, "certificate"))
        self.assertTrue(submission.passed)
        result = self.client.get(f"/results/{submission.pk}/")
        self.assertEqual(result.status_code, 200)
        self.assertNotContains(result, "Keçid balı")
        self.assertNotContains(result, f"{self.exam.passing_score}%")
        self.assertContains(result, "İmtahan Nəticə Vərəqəsi")
        self.assertContains(result, "Ayan")
        self.assertNotContains(result, "Sertifikatı yüklə")
        self.assertNotContains(result, "Sertifikat əldə etmək")
        cert = submission.certificate
        hidden = self.client.get(f"/certificates/{cert.pk}/pdf/")
        self.assertEqual(hidden.status_code, 404)

    def test_certificate_contact_appears_only_on_result_sheet(self):
        settings_obj = SiteSettings.load()
        settings_obj.certificate_contact_phone = "+994501112233"
        settings_obj.save()
        self.client.force_login(self.user)
        taking = self.client.get(f"/exams/{self.exam.pk}/")
        self.assertEqual(taking.status_code, 200)
        self.assertNotContains(taking, "Sertifikat əldə etmək üçün")
        listing = self.client.get("/")
        self.assertNotContains(listing, "Sertifikat əldə etmək üçün")
        self.client.post(
            f"/exams/{self.exam.pk}/",
            {f"q_{self.exam.questions.first().pk}": str(self.correct.pk)},
        )
        submission = self.user.exam_submissions.get(exam=self.exam)
        result = self.client.get(f"/results/{submission.pk}/")
        self.assertContains(result, "Sertifikat əldə etmək üçün bizə yazın")
        self.assertContains(result, "050 111 22 33")
        self.assertContains(result, "https://wa.me/994501112233")


class PanelSiteSettingsTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin_contact", "ac@test.local", "adminpass")
        self.student = complete_student("telebe_contact", phone="+994509990011")

    def test_staff_can_change_certificate_contact_phone(self):
        self.client.force_login(self.admin)
        page = self.client.get("/panel/settings/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sertifikat əlaqəsi")
        response = self.client.post("/panel/settings/", {"certificate_contact_phone": "055 222 33 44"})
        self.assertRedirects(response, "/panel/settings/")
        self.assertEqual(SiteSettings.load().certificate_contact_phone, "+994552223344")

    def test_student_cannot_open_site_settings(self):
        self.client.force_login(self.student)
        response = self.client.get("/panel/settings/")
        self.assertEqual(response.status_code, 302)


class ExamWindowTests(TestCase):
    def setUp(self):
        self.user = complete_student("telebe2")
        self.exam = Exam.objects.create(
            title="Gözləyən imtahan",
            duration_minutes=10,
            is_active=True,
            opens_at=timezone.now() + timedelta(days=1),
        )
        Question.objects.create(exam=self.exam, number=1, text="Sual?")

    def test_student_cannot_start_before_open(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/exams/{self.exam.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.exam.is_available())


class PanelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("admin2", "a2@test.local", "adminpass")
        self.student = user_model.objects.create_user("telebe3", password="test12345")
        self.client.force_login(self.admin)

    def test_dashboard_loads_for_staff(self):
        response = self.client.get("/panel/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yeni imtahan yarat")

    def test_student_is_blocked_from_panel(self):
        self.client.force_login(self.student)
        response = self.client.get("/panel/")
        self.assertEqual(response.status_code, 302)

    def test_create_exam_with_dates_and_pdf(self):
        pdf = SimpleUploadedFile("q.pdf", make_pdf(SAMPLE_TEXT), content_type="application/pdf")
        response = self.client.post(
            "/panel/exams/new/",
            {
                "title": "Panel imtahanı",
                "description": "PDF idxalı",
                "duration_minutes": 40,
                "passing_score": 60,
                "opens_at": "2026-09-05T09:00",
                "closes_at": "2026-09-20T18:00",
                "is_active": "on",
                "answer_key": "1-B, 2-B, 3-C",
                "pdf_file": pdf,
            },
        )
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(title="Panel imtahanı")
        self.assertEqual(exam.questions.count(), 3)
        self.assertEqual(Choice.objects.filter(question__exam=exam, is_correct=True).count(), 0)
        self.assertEqual(exam.passing_score, 60)
        self.assertIsNotNone(exam.opens_at)
        self.assertIsNotNone(exam.closes_at)

    def test_create_exam_without_pdf_opens_question_form(self):
        response = self.client.post(
            "/panel/exams/new/",
            {
                "title": "Əl ilə imtahan",
                "duration_minutes": 30,
                "passing_score": 50,
                "is_active": "on",
            },
        )
        exam = Exam.objects.get(title="Əl ilə imtahan")
        self.assertEqual(exam.questions.count(), 0)
        self.assertRedirects(response, f"/panel/exams/{exam.pk}/questions/new/")

    def test_create_page_says_pdf_is_optional(self):
        response = self.client.get("/panel/exams/new/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yeni imtahan")
        self.assertContains(response, "PDF-dən idxal (istəyə bağlı)")
        self.assertContains(response, "Sualları özünüz yazın")


class AdminImportViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("admin", "admin@test.local", "adminpass")
        self.client.force_login(self.admin)

    def test_import_pdf_creates_exam_without_marking_answers(self):
        pdf = SimpleUploadedFile("q.pdf", make_pdf(SAMPLE_TEXT), content_type="application/pdf")
        response = self.client.post(
            "/admin/exams/exam/import-pdf/",
            {
                "title": "PDF imtahan",
                "description": "Avtomatik idxal",
                "duration_minutes": 30,
                "passing_score": 50,
                "is_active": "on",
                "answer_key": "1-B, 2-B, 3-C",
                "pdf_file": pdf,
            },
        )
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get(title="PDF imtahan")
        self.assertEqual(exam.questions.count(), 3)
        self.assertEqual(Choice.objects.filter(question__exam=exam, is_correct=True).count(), 0)


class BiologyPdfImportTests(TestCase):
    pdf_path = (
        Path(__file__).resolve().parent.parent
        / "media"
        / "exams"
        / "pdfs"
        / "BIOLOGIYA_IIpfntu.pdf"
    )

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parent.parent
            / "media"
            / "exams"
            / "pdfs"
            / "BIOLOGIYA_IIpfntu.pdf"
        ).exists(),
        "real PDF yoxdur",
    )
    def test_biology_pdf_decodes_and_splits_choices(self):
        from exams.services.pdf_parser import (
            _prepare,
            collect_question_regions,
            extract_choice_images,
            extract_pdf_text,
        )

        text = extract_pdf_text(str(self.pdf_path))
        questions = parse_questions(text)
        self.assertGreaterEqual(len(questions), 10)
        q2 = next(item for item in questions if item["number"] == 2)
        self.assertNotIn("SİTUASİYA", q2["text"])
        self.assertNotIn("Ekoloji", q2["text"])
        q5 = next(item for item in questions if item["number"] == 5)
        self.assertFalse(any("BİOLOGİYA" in choice["text"] for choice in q5["choices"]))
        self.assertEqual(q5["choices"][-1]["text"], "1 : 6")
        q6 = next(item for item in questions if item["number"] == 6)
        self.assertTrue(any(">" in choice["text"] for choice in q6["choices"]))
        self.assertIn("|", q6["choices"][0]["text"])

        import pymupdf

        regions = {number: (page_i, rect) for number, page_i, rect in collect_question_regions(str(self.pdf_path))}
        self.assertIn(2, regions)
        self.assertIn(3, regions)
        self.assertIn(6, regions)
        with pymupdf.open(str(self.pdf_path)) as document:
            page_i, rect = regions[2]
            clip_text = _prepare(document[page_i].get_text("text", clip=rect) or "")
            self.assertIn("meyoz", clip_text.lower())
            self.assertNotIn("SİTUASİYA", clip_text)
            page_i, rect = regions[6]
            clip6 = _prepare(document[page_i].get_text("text", clip=rect) or "")
            self.assertIn("karbohidrat", clip6.lower())
            self.assertIn(">", clip6)
        self.assertEqual(len(extract_choice_images(str(self.pdf_path)).get(3, [])), 5)


class PanelExamDeleteTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("admin3", "a3@test.local", "adminpass")
        self.student = complete_student("telebe4")
        self.exam = Exam.objects.create(title="Silinəcək imtahan", duration_minutes=20)
        Question.objects.create(exam=self.exam, number=1, text="Sual?")

    def test_exam_list_has_edit_and_delete_actions(self):
        self.client.force_login(self.admin)
        response = self.client.get("/panel/exams/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Redaktə")
        self.assertContains(response, "Sil")
        self.assertContains(response, f"/panel/exams/{self.exam.pk}/")
        self.assertContains(response, f"/panel/exams/{self.exam.pk}/delete/")

    def test_staff_can_delete_exam(self):
        self.client.force_login(self.admin)
        response = self.client.post(f"/panel/exams/{self.exam.pk}/delete/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Exam.objects.filter(pk=self.exam.pk).exists())

    def test_student_cannot_delete_exam(self):
        self.client.force_login(self.student)
        response = self.client.post(f"/panel/exams/{self.exam.pk}/delete/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Exam.objects.filter(pk=self.exam.pk).exists())


class PanelQuestionEditTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("admin4", "a4@test.local", "adminpass")
        self.student = complete_student("telebe5", phone="+994557778899")
        self.exam = Exam.objects.create(title="Kimya sınağı", duration_minutes=20)
        self.question = Question.objects.create(exam=self.exam, number=1, text="Köhnə sual")
        self.choice_a = Choice.objects.create(
            question=self.question, letter="A", text="bir", is_correct=False
        )
        self.choice_b = Choice.objects.create(
            question=self.question, letter="B", text="iki", is_correct=True
        )

    def test_exam_page_links_to_question_editor(self):
        self.client.force_login(self.admin)
        response = self.client.get(f"/panel/exams/{self.exam.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/panel/exams/{self.exam.pk}/questions/{self.question.pk}/")
        self.assertContains(response, "Sual əlavə et")
        self.assertContains(response, f"/panel/exams/{self.exam.pk}/questions/new/")
        self.assertContains(response, f"/panel/exams/{self.exam.pk}/questions/screenshot/")
        self.assertContains(response, "PDF skrin")
        self.assertContains(response, "Sil")

    def _png(self, name="q44.png"):
        from io import BytesIO
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (12, 12), (20, 80, 180)).save(buffer, "PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_staff_can_upload_screenshot_as_missing_question_number(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/screenshot/",
            {"number": "44", "image": self._png()},
        )
        self.assertRedirects(response, f"/panel/exams/{self.exam.pk}/#sual-44")
        question = Question.objects.get(exam=self.exam, number=44)
        self.assertTrue(question.image)
        self.assertEqual(
            list(question.choices.order_by("letter").values_list("letter", flat=True)),
            ["A", "B", "C", "D"],
        )

    def test_staff_can_replace_existing_question_with_screenshot(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/screenshot/",
            {"number": "1", "image": self._png("q1.png")},
        )
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "Sual 1")
        self.assertTrue(self.question.image)
        self.choice_a.refresh_from_db()
        self.choice_b.refresh_from_db()
        self.assertEqual(self.choice_a.text, "")
        self.assertEqual(self.choice_b.text, "")
        self.assertTrue(self.choice_b.is_correct)
        self.assertFalse(self.choice_a.is_correct)

    def test_staff_can_delete_question_from_exam_page(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/{self.question.pk}/delete/"
        )
        self.assertRedirects(response, f"/panel/exams/{self.exam.pk}/#suallar")
        self.assertFalse(Question.objects.filter(pk=self.question.pk).exists())

    def test_student_cannot_upload_screenshot(self):
        self.client.force_login(self.student)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/screenshot/",
            {"number": "44", "image": self._png()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Question.objects.filter(exam=self.exam, number=44).exists())

    def test_staff_can_open_manual_question_form(self):
        self.client.force_login(self.admin)
        response = self.client.get(f"/panel/exams/{self.exam.pk}/questions/new/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yeni sual")
        self.assertContains(response, "Saxla və növbəti sual")

    def test_staff_can_add_question_manually(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/new/",
            {
                "number": "2",
                "text": "Əl ilə yazılmış sual",
                "choices-TOTAL_FORMS": "5",
                "choices-INITIAL_FORMS": "0",
                "choices-MIN_NUM_FORMS": "0",
                "choices-MAX_NUM_FORMS": "5",
                "choices-0-letter": "A",
                "choices-0-text": "birinci",
                "choices-1-letter": "B",
                "choices-1-text": "ikinci",
                "choices-1-is_correct": "on",
                "choices-2-letter": "C",
                "choices-2-text": "üçüncü",
                "choices-3-letter": "D",
                "choices-3-text": "",
                "choices-4-letter": "E",
                "choices-4-text": "",
            },
        )
        self.assertRedirects(response, f"/panel/exams/{self.exam.pk}/#suallar")
        question = Question.objects.get(exam=self.exam, number=2)
        self.assertEqual(question.text, "Əl ilə yazılmış sual")
        self.assertEqual(
            list(question.choices.order_by("letter").values_list("letter", "text")),
            [("A", "birinci"), ("B", "ikinci"), ("C", "üçüncü")],
        )
        self.assertTrue(question.choices.get(letter="B").is_correct)

    def test_staff_can_save_and_add_another_question(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/new/",
            {
                "number": "2",
                "text": "Növbəti üçün saxla",
                "add_another": "1",
                "choices-TOTAL_FORMS": "5",
                "choices-INITIAL_FORMS": "0",
                "choices-MIN_NUM_FORMS": "0",
                "choices-MAX_NUM_FORMS": "5",
                "choices-0-letter": "A",
                "choices-0-text": "cavab",
            },
        )
        self.assertRedirects(response, f"/panel/exams/{self.exam.pk}/questions/new/")
        self.assertTrue(Question.objects.filter(exam=self.exam, number=2).exists())

    def test_staff_can_edit_question_and_choices(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/{self.question.pk}/",
            {
                "number": "1",
                "text": "Yenilənmiş sual",
                "choices-TOTAL_FORMS": "2",
                "choices-INITIAL_FORMS": "2",
                "choices-MIN_NUM_FORMS": "0",
                "choices-MAX_NUM_FORMS": "5",
                "choices-0-id": str(self.choice_a.pk),
                "choices-0-letter": "A",
                "choices-0-text": "yeni A",
                "choices-1-id": str(self.choice_b.pk),
                "choices-1-letter": "B",
                "choices-1-text": "yeni B",
                "choices-1-is_correct": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        self.choice_a.refresh_from_db()
        self.choice_b.refresh_from_db()
        self.assertEqual(self.question.text, "Yenilənmiş sual")
        self.assertEqual(self.choice_a.text, "yeni A")
        self.assertEqual(self.choice_b.text, "yeni B")
        self.assertTrue(self.choice_b.is_correct)
        self.assertFalse(self.choice_a.is_correct)

    def test_student_cannot_edit_question(self):
        self.client.force_login(self.student)
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/questions/{self.question.pk}/",
            {"number": "1", "text": "hack"},
        )
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "Köhnə sual")


class ScoringRuleTests(TestCase):
    def setUp(self):
        self.exam = Exam.objects.create(title="Bal imtahanı", default_points=10)
        subject = Subject.objects.get(name="Riyaziyyat")
        self.q1 = Question.objects.create(exam=self.exam, number=1, text="Ümumi bal", points=None, subject=subject)
        self.q2 = Question.objects.create(exam=self.exam, number=2, text="Öz balı", points=3, subject=subject)
        Choice.objects.create(question=self.q1, letter="A", text="a", is_correct=True)
        Choice.objects.create(question=self.q2, letter="A", text="a", is_correct=False)

    def test_question_points_override_exam_default(self):
        from exams.services.scoring import effective_points, question_warnings, score_answers

        self.assertEqual(effective_points(self.q1), 10)
        self.assertEqual(effective_points(self.q2), 3)
        self.assertEqual(question_warnings(self.q1), [])
        self.assertIn("Düzgün cavab", question_warnings(self.q2)[0])
        earned, maximum, percent = score_answers(
            [self.q1, self.q2],
            {self.q1.pk: self.q1.choices.get(letter="A"), self.q2.pk: None},
        )
        self.assertEqual(earned, 10)
        self.assertEqual(maximum, 13)
        self.assertEqual(percent, round(10 / 13 * 100, 2))

    def test_star_answer_any_choice_is_correct_blank_is_not(self):
        from exams.services.scoring import correct_letter, score_answers

        Choice.objects.filter(question=self.q2).update(is_correct=True)
        Choice.objects.create(question=self.q2, letter="B", text="b", is_correct=True)
        Choice.objects.create(question=self.q2, letter="C", text="c", is_correct=True)
        self.assertEqual(correct_letter(self.q2), "*")
        pick_c = self.q2.choices.get(letter="C")
        earned, maximum, _percent = score_answers([self.q2], {self.q2.pk: pick_c})
        self.assertEqual(earned, 3)
        self.assertEqual(maximum, 3)
        earned_blank, _, _ = score_answers([self.q2], {self.q2.pk: None})
        self.assertEqual(earned_blank, 0)

    def test_warns_when_no_points_anywhere(self):
        from exams.services.scoring import question_warnings

        self.exam.default_points = None
        self.exam.save(update_fields=["default_points"])
        self.q1.points = None
        self.q1.save(update_fields=["points"])
        warnings = question_warnings(self.q1)
        self.assertTrue(any("Bal təyin edilməyib" in item for item in warnings))


class ExamSettingsAndMarkingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser("admin5", "a5@test.local", "adminpass")
        self.exam = Exam.objects.create(title="Tənzimlənən", duration_minutes=40, default_points=10)
        self.question = Question.objects.create(exam=self.exam, number=1, text="Sual mətn")
        self.choice_a = Choice.objects.create(question=self.question, letter="A", text="bir")
        self.choice_b = Choice.objects.create(question=self.question, letter="B", text="iki")
        self.client.force_login(self.admin)

    def test_list_and_detail_have_settings_link(self):
        listing = self.client.get("/panel/exams/")
        detail = self.client.get(f"/panel/exams/{self.exam.pk}/")
        self.assertContains(listing, "Tənzimləmə")
        self.assertContains(listing, f"/panel/exams/{self.exam.pk}/settings/")
        self.assertContains(detail, f"/panel/exams/{self.exam.pk}/settings/")
        self.assertContains(detail, "Düzgün cavab təyin edilməyib")

    def test_save_settings_unlimited_time_and_public_access(self):
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/settings/",
            {
                "default_points": "10",
                "unlimited_time": "on",
                "duration_minutes": "40",
                "access_mode": "public",
                "max_attempts": "2",
                "passing_score": "50",
                "shuffle_questions": "on",
                "show_score_immediately": "on",
                "show_correct_answers": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.exam.refresh_from_db()
        self.assertIsNone(self.exam.duration_minutes)
        self.assertEqual(self.exam.access_mode, Exam.ACCESS_PUBLIC)
        self.assertTrue(self.exam.shuffle_questions)
        self.assertEqual(self.exam.max_attempts, 2)

    def test_set_correct_answer_and_question_points(self):
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/marking/",
            {
                f"correct_{self.question.pk}": "B",
                f"points_{self.question.pk}": "7",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.choice_a.refresh_from_db()
        self.choice_b.refresh_from_db()
        self.question.refresh_from_db()
        self.assertFalse(self.choice_a.is_correct)
        self.assertTrue(self.choice_b.is_correct)
        self.assertEqual(self.question.points, 7)

    def test_star_answers_option_accepts_any_selected_choice(self):
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/marking/",
            {
                f"correct_{self.question.pk}": "*",
                f"points_{self.question.pk}": "5",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.choice_a.refresh_from_db()
        self.choice_b.refresh_from_db()
        self.assertTrue(self.choice_a.is_correct)
        self.assertTrue(self.choice_b.is_correct)
        page = self.client.get(f"/panel/exams/{self.exam.pk}/")
        self.assertContains(page, "* cavablar")
        self.assertContains(page, 'value="*"')
        self.assertRegex(page.content.decode(), r'<option value="\*"[^>]*selected')

        student = complete_student("ulduzci", phone="+994509998877")
        self.client.force_login(student)
        submit = self.client.post(
            f"/exams/{self.exam.pk}/",
            {f"q_{self.question.pk}": str(self.choice_a.pk)},
        )
        self.assertEqual(submit.status_code, 302)
        submission = student.exam_submissions.get(exam=self.exam)
        self.assertEqual(float(submission.score), 100.0)
        self.assertEqual(submission.earned_points, 5)

    def test_assign_subject_per_question_and_range(self):
        math = Subject.objects.get(name="Riyaziyyat")
        az = Subject.objects.get(name="Azərbaycan dili")
        q2 = Question.objects.create(exam=self.exam, number=2, text="İkinci")
        Choice.objects.create(question=q2, letter="A", text="x")
        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/marking/",
            {
                f"correct_{self.question.pk}": "B",
                f"points_{self.question.pk}": "7",
                f"subject_{self.question.pk}": str(az.pk),
                f"correct_{q2.pk}": "A",
                f"points_{q2.pk}": "3",
                f"subject_{q2.pk}": str(math.pk),
                "action": "save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        q2.refresh_from_db()
        self.assertEqual(self.question.subject_id, az.pk)
        self.assertEqual(q2.subject_id, math.pk)

        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/marking/",
            {
                "action": "bulk_range",
                "range_from": "1",
                "range_to": "2",
                "bulk_subject": str(math.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        q2.refresh_from_db()
        self.assertEqual(self.question.subject_id, math.pk)
        self.assertEqual(q2.subject_id, math.pk)

        response = self.client.post(
            f"/panel/exams/{self.exam.pk}/marking/",
            {
                "action": "bulk_selected",
                "selected": [str(self.question.pk)],
                "bulk_subject": str(az.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.question.refresh_from_db()
        q2.refresh_from_db()
        self.assertEqual(self.question.subject_id, az.pk)
        self.assertEqual(q2.subject_id, math.pk)


class PublicExamAccessTests(TestCase):
    def setUp(self):
        self.public = Exam.objects.create(
            title="Açıq imtahan",
            is_active=True,
            access_mode=Exam.ACCESS_PUBLIC,
        )
        self.private = Exam.objects.create(
            title="Qapalı imtahan",
            is_active=True,
            access_mode=Exam.ACCESS_REGISTERED,
        )

    def test_guest_sees_only_public_exams(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Açıq imtahan")
        self.assertNotContains(response, "Qapalı imtahan")
        self.assertNotContains(response, "keçid")


class RegistrationAndProfileTests(TestCase):
    def setUp(self):
        self.exam = Exam.objects.create(title="Fizika", duration_minutes=15, is_active=True)
        Question.objects.create(exam=self.exam, number=1, text="Sual?")

    def test_register_requires_phone_and_district(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "yeni",
                "password1": "GucluSifre123",
                "password2": "GucluSifre123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="yeni").exists())

    def test_register_with_phone_and_district_creates_profile(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "yeni",
                "first_name": "Nuray",
                "last_name": "Bağırsoy",
                "password1": "GucluSifre123",
                "password2": "GucluSifre123",
                "phone": "050 111 22 33",
                "grade": "5",
                "region": "Bakı",
                "baku_district": "Yasamal",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="yeni")
        self.assertEqual(user.profile.phone, "+994501112233")
        self.assertEqual(user.profile.region, "Bakı")
        self.assertEqual(user.profile.baku_district, "Yasamal")
        self.assertEqual(user.profile.grade, 5)
        self.assertEqual(user.profile.first_name, "Nuray")
        self.assertTrue(user.profile.code)

    def test_register_allows_simple_four_character_password(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "sadesifre",
                "first_name": "Nuray",
                "last_name": "Bağırsoy",
                "password1": "test",
                "password2": "test",
                "phone": "050 333 44 55",
                "grade": "5",
                "region": "Bakı",
                "baku_district": "Yasamal",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username="sadesifre").exists())

    def test_register_rejects_password_shorter_than_four(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "qisasifre",
                "first_name": "Nuray",
                "last_name": "Bağırsoy",
                "password1": "abc",
                "password2": "abc",
                "phone": "050 333 44 66",
                "grade": "5",
                "region": "Bakı",
                "baku_district": "Yasamal",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="qisasifre").exists())

    def test_register_other_region_requires_address(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "gence",
                "first_name": "Ali",
                "last_name": "Quliyev",
                "password1": "GucluSifre123",
                "password2": "GucluSifre123",
                "phone": "050 222 33 44",
                "grade": "7",
                "region": "Gəncə",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="gence").exists())

        response = self.client.post(
            "/accounts/register/",
            {
                "username": "gence",
                "first_name": "Ali",
                "last_name": "Quliyev",
                "password1": "GucluSifre123",
                "password2": "GucluSifre123",
                "phone": "050 222 33 44",
                "grade": "7",
                "region": "Gəncə",
                "address": "Nizami küçəsi 10",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="gence")
        self.assertEqual(user.profile.region, "Gəncə")
        self.assertEqual(user.profile.address, "Nizami küçəsi 10")
        self.assertEqual(user.profile.baku_district, "")

    def test_invalid_phone_is_rejected(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "username": "yeni",
                "first_name": "A",
                "last_name": "B",
                "password1": "GucluSifre123",
                "password2": "GucluSifre123",
                "phone": "12345",
                "grade": "5",
                "region": "Bakı",
                "baku_district": "Yasamal",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="yeni").exists())

    def test_cannot_take_exam_without_phone_and_district(self):
        user = get_user_model().objects.create_user("natamam", password="test12345")
        self.client.force_login(user)
        response = self.client.get(f"/exams/{self.exam.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/profile/", response["Location"])
        self.assertFalse(ExamSubmission.objects.filter(user=user, exam=self.exam).exists())


class ParticipantSheetTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin6", "a6@test.local", "adminpass")
        self.exam = Exam.objects.create(title="5-ci sinif sınağı", grade=5, is_active=True, default_points=10)
        self.az = Subject.objects.get(name="Azərbaycan dili")
        self.math = Subject.objects.get(name="Riyaziyyat")
        q1 = Question.objects.create(exam=self.exam, number=1, text="Az 1", subject=self.az)
        q2 = Question.objects.create(exam=self.exam, number=2, text="Riy 1", subject=self.math)
        self.c1 = Choice.objects.create(question=q1, letter="A", text="düz", is_correct=True)
        Choice.objects.create(question=q1, letter="B", text="səhv", is_correct=False)
        Choice.objects.create(question=q2, letter="C", text="düz", is_correct=True)
        self.c2w = Choice.objects.create(question=q2, letter="D", text="səhv", is_correct=False)
        self.s5 = complete_student("besinci", phone="+994501110001", grade=5, first_name="Nuray", last_name="Bağırsoy")
        self.s7 = complete_student(
            "yeddinci",
            phone="+994501110002",
            grade=7,
            first_name="Ali",
            last_name="Quliyev",
            region="Gəncə",
            baku_district="",
            address="Nizami 1",
        )

    def _finish(self, user, answers):
        self.client.force_login(user)
        payload = {}
        for question, choice in answers:
            payload[f"q_{question.pk}"] = str(choice.pk)
        self.client.post(f"/exams/{self.exam.pk}/", payload)
        self.client.logout()

    def test_participants_filter_and_answer_sheet(self):
        q1 = self.exam.questions.get(number=1)
        q2 = self.exam.questions.get(number=2)
        self._finish(self.s5, [(q1, self.c1), (q2, self.c2w)])
        self._finish(self.s7, [(q1, self.c1), (q2, q2.choices.get(letter="C"))])

        self.client.force_login(self.admin)
        listing = self.client.get(f"/panel/exams/{self.exam.pk}/participants/")
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Nuray")
        self.assertContains(listing, "Ali")

        only_fifth = self.client.get(f"/panel/exams/{self.exam.pk}/participants/?grade=5")
        self.assertContains(only_fifth, "Nuray")
        self.assertNotContains(only_fifth, "Ali")

        gence = self.client.get(f"/panel/exams/{self.exam.pk}/participants/?region=Gəncə")
        self.assertContains(gence, "Ali")
        self.assertNotContains(gence, "Nuray")

        sub = self.s5.exam_submissions.get(exam=self.exam)
        sheet = self.client.get(f"/panel/exams/{self.exam.pk}/submissions/{sub.pk}/")
        self.assertEqual(sheet.status_code, 200)
        self.assertContains(sheet, "İmtahan Nəticə Vərəqəsi")
        self.assertContains(sheet, "Azərbaycan dili")
        self.assertContains(sheet, "Riyaziyyat")
        self.assertContains(sheet, "Nuray")



