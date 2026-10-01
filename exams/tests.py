from datetime import timedelta
from pathlib import Path
import unittest

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from exams.models import Choice, Exam, ExamSubmission, Question, StudentProfile, Subject
from exams.services.pdf_parser import (
    ParseError,
    apply_answer_key,
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



