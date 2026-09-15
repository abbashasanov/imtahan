# Onlayn sınaq imtahanı platforması

Django 5 əsaslı platforma. Admin PDF yükləyəndə suallar regex ilə parse olunub `Exam`, `Question` və `Choice` modellərinə yazılır.

## Texnologiyalar

- Python 3.11+
- Django 5
- `pdfplumber` + `PyMuPDF` (mətn çıxarışı)
- SQLite (inkişaf); istehsal üçün PostgreSQL-ə keçmək olar

## Quraşdırma

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Admin: http://127.0.0.1:8000/admin/
- Tələbə paneli: http://127.0.0.1:8000/

## PDF idxalı

Admin → İmtahanlar → **PDF-dən idxal et** (və ya imtahan formasındakı PDF sahəsi).

Gözlənilən sual formatı:

```
1. Sual mətni
A) variant
B) variant
C) variant
D) variant
E) variant

Sual 2: İkinci sual
A) ...
```

Cavab açarı (istəyə bağlı): `1-A, 2-C, 3-D`

Açar verilərsə, müvafiq `Choice.is_correct` avtomatik `True` olur.

## Arxitektura

```
PDF → extract_pdf_text (pdfplumber / PyMuPDF)
    → parse_questions / parse_answer_key
    → transaction.atomic → Exam, Question, Choice
Tələbə → ExamSubmission + UserAnswer → yekun bal
```

Əsas parser: `exams/services/pdf_parser.py`
