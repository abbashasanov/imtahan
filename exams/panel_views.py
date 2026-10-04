from datetime import timedelta
from functools import wraps
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from exams.forms import (
    ExamSettingsForm,
    PanelExamForm,
    QuestionChoiceCreateFormSet,
    QuestionChoiceFormSet,
    QuestionEditForm,
    QuestionScreenshotForm,
    SiteSettingsForm,
)
from exams.models import Certificate, Choice, Exam, ExamSubmission, Question, SiteSettings, Subject
from exams.regions import BAKU, GRADE_CHOICES, grade_label
from exams.services.scoring import (
    answer_sheet_payload,
    correct_letter,
    effective_points,
    question_warnings,
    ranked_submissions,
)
from exams.services.certificates import build_certificate_pdf, issue_certificate_if_passed
from exams.services.export import xlsx_response


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "Bu səhifə yalnız inzibatçılar üçündür.")
            return redirect("exam_list")
        return view(request, *args, **kwargs)

    return wrapped


def _save_exam_from_form(form, parse_requested=False):
    exam = form.save()
    parse_pdf = parse_requested or form.cleaned_data.get("parse_pdf")
    stats = None
    if parse_pdf and exam.pdf_file:
        stats = import_exam_from_pdf(exam, exam.pdf_file)
    return exam, stats


@staff_required
def dashboard(request):
    now = timezone.now()
    selected = parse_date(request.GET.get("date") or "") or timezone.localdate()
    exams = Exam.objects.all()
    day_exams = []
    for exam in exams.filter(is_active=True):
        opens = timezone.localtime(exam.opens_at).date() if exam.opens_at else None
        closes = timezone.localtime(exam.closes_at).date() if exam.closes_at else None
        if opens and opens > selected:
            continue
        if closes and closes < selected:
            continue
        day_exams.append(exam)

    submissions = ExamSubmission.objects.filter(is_completed=True)
    context = {
        "exam_count": exams.count(),
        "open_count": sum(1 for exam in exams if exam.is_available()),
        "result_count": submissions.count(),
        "certificate_count": Certificate.objects.count(),
        "avg_score": submissions.aggregate(avg=Avg("score"))["avg"] or 0,
        "recent_results": submissions.select_related("user", "exam")[:6],
        "upcoming": exams.filter(is_active=True, opens_at__gt=now).order_by("opens_at")[:5],
        "day_exams": day_exams,
        "selected_date": selected.isoformat(),
        "prev_date": (selected - timedelta(days=1)).isoformat(),
        "next_date": (selected + timedelta(days=1)).isoformat(),
    }
    return render(request, "panel/dashboard.html", context)


@staff_required
def exam_list(request):
    exams = Exam.objects.annotate(
        submission_total=Count("submissions", filter=Q(submissions__is_completed=True)),
        question_total=Count("questions", distinct=True),
    )
    return render(request, "panel/exam_list.html", {"exams": exams})


@staff_required
def exam_create(request):
    if request.method == "POST":
        form = PanelExamForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                exam, stats = _save_exam_from_form(form, parse_requested=bool(form.cleaned_data.get("pdf_file")))
            except ParseError as exc:
                form.add_error("pdf_file", str(exc))
            else:
                if stats:
                    messages.success(
                        request,
                        f"«{exam.title}» yaradıldı. {stats['questions']} sual, {stats['choices']} variant yazıldı. Düzgün cavabları aşağıda təyin edin.",
                    )
                    return redirect("panel_exam_detail", pk=exam.pk)
                messages.success(
                    request,
                    f"«{exam.title}» yaradıldı. İndi sual əlavə edin və ya sonra PDF yükləyin.",
                )
                return redirect("panel_question_create", exam_pk=exam.pk)
    else:
        form = PanelExamForm()
    return render(request, "panel/exam_form.html", {"form": form, "mode": "create"})


@staff_required
def exam_delete(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == "POST":
        title = exam.title
        exam.delete()
        messages.success(request, f"«{title}» imtahanı silindi.")
        return redirect("panel_exams")
    return render(request, "panel/exam_confirm_delete.html", {"exam": exam})


@staff_required
def exam_detail(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == "POST":
        form = PanelExamForm(request.POST, request.FILES, instance=exam)
        if form.is_valid():
            try:
                exam, stats = _save_exam_from_form(
                    form,
                    parse_requested=request.POST.get("import_mode") == "replace"
                    and bool(form.cleaned_data.get("pdf_file")),
                )
            except ParseError as exc:
                form.add_error("pdf_file", str(exc))
            else:
                if stats:
                    messages.success(
                        request,
                        f"Yeniləndi. {stats['questions']} sual idxal olundu. Düzgün cavabları aşağıda təyin edin.",
                    )
                else:
                    messages.success(request, "İmtahan yeniləndi.")
                return redirect("panel_exam_detail", pk=exam.pk)
    else:
        form = PanelExamForm(instance=exam)

    results = exam.submissions.filter(is_completed=True).select_related(
        "user", "user__profile", "certificate"
    ).order_by("-submitted_at")
    questions = exam.questions.select_related("subject").prefetch_related("choices")
    marked_questions = []
    for question in questions:
        marked_questions.append(
            {
                "question": question,
                "correct": correct_letter(question),
                "effective_points": effective_points(question),
                "warnings": question_warnings(question),
            }
        )
    return render(
        request,
        "panel/exam_form.html",
        {
            "form": form,
            "mode": "edit",
            "exam": exam,
            "results": results,
            "questions": questions,
            "marked_questions": marked_questions,
            "subjects": Subject.objects.all(),
            "screenshot_form": QuestionScreenshotForm(),
        },
    )


@staff_required
def question_edit(request, exam_pk, pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    question = get_object_or_404(Question, pk=pk, exam=exam)
    if request.method == "POST":
        form = QuestionEditForm(request.POST, request.FILES, instance=question)
        formset = QuestionChoiceFormSet(
            request.POST, request.FILES, instance=question, prefix="choices"
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Sual {question.number} yeniləndi.")
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
    else:
        form = QuestionEditForm(instance=question)
        formset = QuestionChoiceFormSet(instance=question, prefix="choices")
    return render(
        request,
        "panel/question_form.html",
        {"exam": exam, "question": question, "form": form, "formset": formset},
    )


@staff_required
def question_create(request, exam_pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    next_number = (exam.questions.aggregate(max_n=Max("number")).get("max_n") or 0) + 1
    question = Question(exam=exam, number=next_number)
    if request.method == "POST":
        form = QuestionEditForm(request.POST, request.FILES, instance=question)
        formset = QuestionChoiceCreateFormSet(
            request.POST, request.FILES, instance=question, prefix="choices"
        )
        if form.is_valid() and formset.is_valid():
            question = form.save(commit=False)
            question.exam = exam
            question.save()
            formset.instance = question
            formset.save()
            messages.success(request, f"Sual {question.number} əlavə olundu.")
            if request.POST.get("add_another"):
                return redirect("panel_question_create", exam_pk=exam.pk)
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
    else:
        form = QuestionEditForm(instance=question)
        formset = QuestionChoiceCreateFormSet(
            instance=question,
            prefix="choices",
            initial=[{"letter": letter} for letter in "ABCDE"],
        )
    return render(
        request,
        "panel/question_form.html",
        {"exam": exam, "question": question, "form": form, "formset": formset},
    )


def _ensure_choice_letters(question, letters="ABCD"):
    existing = set(question.choices.values_list("letter", flat=True))
    for letter in letters:
        if letter not in existing:
            Choice.objects.create(question=question, letter=letter, text="", is_correct=False)


def _clear_choice_content(question):
    for choice in question.choices.all():
        if choice.image:
            choice.image.delete(save=False)
        choice.text = ""
        choice.image = ""
        choice.save(update_fields=["text", "image"])


@staff_required
def question_screenshot(request, exam_pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    if request.method != "POST":
        return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
    form = QuestionScreenshotForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Sual nömrəsi və skrin şəklini seçin.")
        return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
    number = form.cleaned_data["number"]
    image = form.cleaned_data["image"]
    question, created = Question.objects.get_or_create(
        exam=exam,
        number=number,
        defaults={"text": f"Sual {number}"},
    )
    if not created:
        question.text = f"Sual {number}"
        question.save(update_fields=["text"])
        _clear_choice_content(question)
    suffix = Path(getattr(image, "name", "") or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".png"
    question.image.save(f"exam{exam.pk}_q{number}{suffix}", image, save=True)
    _ensure_choice_letters(question)
    if created:
        messages.success(request, f"Sual {number} skrinlə əlavə olundu. Düzgün cavabı aşağıda işarələyin.")
    else:
        messages.success(request, f"Sual {number} skrinlə əvəz olundu. Düzgün cavabı yoxlayın.")
    return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#sual-{question.number}")


@staff_required
def question_delete(request, exam_pk, pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    question = get_object_or_404(Question, pk=pk, exam=exam)
    if request.method == "POST":
        number = question.number
        question.delete()
        messages.success(request, f"Sual {number} silindi.")
        return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
    return redirect("panel_question_edit", exam_pk=exam.pk, pk=question.pk)


@staff_required
def exam_settings(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == "POST":
        form = ExamSettingsForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            messages.success(request, f"«{exam.title}» tənzimləmələri yadda saxlanıldı.")
            return redirect("panel_exam_settings", pk=exam.pk)
    else:
        form = ExamSettingsForm(instance=exam)
    return render(request, "panel/exam_settings.html", {"exam": exam, "form": form})


@staff_required
def exam_marking(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method != "POST":
        return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
    action = request.POST.get("action") or "save"
    questions = exam.questions.prefetch_related("choices")

    def resolve_subject(raw):
        raw = (raw or "").strip()
        if not raw:
            return None, True
        try:
            subject = Subject.objects.get(pk=int(raw))
        except (ValueError, Subject.DoesNotExist):
            return None, False
        return subject, True

    if action == "bulk_range":
        subject, ok = resolve_subject(request.POST.get("bulk_subject"))
        if not ok:
            messages.error(request, "Fənn tapılmadı.")
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
        try:
            start = int(request.POST.get("range_from") or 0)
            end = int(request.POST.get("range_to") or 0)
        except ValueError:
            messages.error(request, "Sual aralığı rəqəm olmalıdır.")
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
        if start < 1 or end < start:
            messages.error(request, "Sual aralığını düzgün yazın (məsələn 1–30).")
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
        updated = exam.questions.filter(number__gte=start, number__lte=end).update(
            subject=subject
        )
        label = subject.name if subject else "boş"
        messages.success(request, f"{updated} suala «{label}» fənni təyin olundu.")
        return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")

    if action == "bulk_selected":
        subject, ok = resolve_subject(request.POST.get("bulk_subject"))
        if not ok:
            messages.error(request, "Fənn tapılmadı.")
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
        ids = [value for value in request.POST.getlist("selected") if value.isdigit()]
        updated = exam.questions.filter(pk__in=ids).update(subject=subject)
        label = subject.name if subject else "boş"
        messages.success(request, f"{updated} suala «{label}» fənni təyin olundu.")
        return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")

    for question in questions:
        letter = (request.POST.get(f"correct_{question.pk}") or "").strip().upper()
        raw_points = (request.POST.get(f"points_{question.pk}") or "").strip()
        subject, ok = resolve_subject(request.POST.get(f"subject_{question.pk}"))
        if not ok:
            messages.error(request, f"Sual {question.number}: fənn tapılmadı.")
            return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
        if letter == "*":
            question.choices.update(is_correct=True)
        elif letter in dict(Choice.LETTERS):
            question.choices.update(is_correct=False)
            question.choices.filter(letter=letter).update(is_correct=True)
        elif letter == "":
            question.choices.update(is_correct=False)
        if raw_points == "":
            question.points = None
        else:
            try:
                value = int(raw_points)
            except ValueError:
                messages.error(request, f"Sual {question.number}: bal rəqəm olmalıdır.")
                return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
            if value < 0:
                messages.error(request, f"Sual {question.number}: bal mənfi ola bilməz.")
                return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")
            question.points = value
        question.subject = subject
        question.save(update_fields=["points", "subject"])
    messages.success(request, "Düzgün cavablar, ballar və fənlər yadda saxlanıldı.")
    return redirect(f"{reverse('panel_exam_detail', args=[exam.pk])}#suallar")


def _area_choices():
    from exams.regions import BAKU_DISTRICTS, CITIES, RAYONS

    choices = [(BAKU, BAKU)]
    for name in BAKU_DISTRICTS:
        choices.append((f"{BAKU} — {name}", f"{BAKU} — {name}"))
    for name in CITIES + RAYONS:
        choices.append((name, name))
    return choices


def _filter_by_area(queryset, region, *, profile_prefix="user__profile"):
    if not region:
        return queryset
    if region.startswith(f"{BAKU} — "):
        district = region.split(" — ", 1)[1]
        return queryset.filter(
            **{
                f"{profile_prefix}__region": BAKU,
                f"{profile_prefix}__baku_district": district,
            }
        )
    return queryset.filter(**{f"{profile_prefix}__region": region})


def _filter_participants(queryset, request):
    grade = request.GET.get("grade") or ""
    region = request.GET.get("region") or ""
    if grade.isdigit():
        queryset = queryset.filter(user__profile__grade=int(grade))
    queryset = _filter_by_area(queryset, region)
    return queryset, grade, region


@staff_required
def exam_participants(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    view = request.GET.get("view") or "list"
    if view not in {"list", "rank", "contact", "groups"}:
        view = "list"
    queryset = exam.submissions.filter(is_completed=True).select_related(
        "user", "user__profile", "certificate"
    )
    queryset, grade, region = _filter_participants(queryset, request)
    ranked = ranked_submissions(queryset)
    grade_groups = []
    area_groups = []
    if view == "groups":
        by_grade = {}
        by_area = {}
        for item in ranked:
            profile = getattr(item.user, "profile", None)
            grade_key = grade_label(profile.grade) if profile and profile.grade else "Sinif yoxdur"
            area_key = profile.area_label if profile else "—"
            by_grade.setdefault(grade_key, []).append(item)
            by_area.setdefault(area_key, []).append(item)
        grade_groups = [{"label": key, "items": value} for key, value in by_grade.items()]
        area_groups = [{"label": key, "items": value} for key, value in by_area.items()]
    return render(
        request,
        "panel/participants.html",
        {
            "exam": exam,
            "view": view,
            "participants": ranked,
            "grade_groups": grade_groups,
            "area_groups": area_groups,
            "selected_grade": grade,
            "selected_region": region,
            "grade_choices": GRADE_CHOICES,
            "area_choices": _area_choices(),
        },
    )


@staff_required
def exam_submission_sheet(request, exam_pk, pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    submission = get_object_or_404(
        ExamSubmission.objects.select_related("exam", "user", "user__profile"),
        pk=pk,
        exam=exam,
        is_completed=True,
    )
    payload = answer_sheet_payload(submission)
    certificate = Certificate.objects.filter(submission=submission).first()
    return render(
        request,
        "panel/answer_sheet.html",
        {
            **payload,
            "exam": exam,
            "certificate": certificate,
            "show_score": True,
            "show_answers": True,
            "staff_view": True,
        },
    )


@staff_required
def result_list(request):
    exam_id = request.GET.get("exam")
    results = ExamSubmission.objects.filter(is_completed=True).select_related(
        "user", "user__profile", "exam", "certificate"
    )
    if exam_id:
        results = results.filter(exam_id=exam_id)
    return render(
        request,
        "panel/results.html",
        {
            "results": results,
            "exams": Exam.objects.all(),
            "selected_exam": exam_id,
        },
    )


@staff_required
def certificate_list(request):
    certificates = Certificate.objects.select_related("submission__user", "submission__exam")
    return render(request, "panel/certificates.html", {"certificates": certificates})


@staff_required
def certificate_issue(request, pk):
    submission = get_object_or_404(ExamSubmission, pk=pk, is_completed=True)
    certificate = issue_certificate_if_passed(submission)
    if certificate:
        messages.success(request, f"{certificate.code} sertifikatı verildi.")
        return redirect("panel_certificate_view", pk=certificate.pk)
    messages.error(request, "Keçid balı toplanmayıb, sertifikat verilə bilməz.")
    return redirect("panel_results")


@staff_required
def certificate_view(request, pk):
    certificate = get_object_or_404(
        Certificate.objects.select_related("submission__user", "submission__exam"),
        pk=pk,
    )
    return render(request, "panel/certificate_print.html", {"certificate": certificate})


@staff_required
def certificate_pdf(request, pk):
    certificate = get_object_or_404(
        Certificate.objects.select_related("submission__user", "submission__exam"),
        pk=pk,
    )
    response = HttpResponse(build_certificate_pdf(certificate), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{certificate.code}.pdf"'
    return response


def _registered_students():
    return get_user_model().objects.filter(is_staff=False, profile__isnull=False).select_related(
        "profile"
    )


def _month_start():
    now = timezone.localtime()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@staff_required
def user_list(request):
    students = _registered_students().order_by("-date_joined", "username")
    total_count = students.count()
    month_count = students.filter(date_joined__gte=_month_start()).count()

    grade = request.GET.get("grade") or ""
    region = request.GET.get("region") or ""
    filtered = students
    if grade.isdigit():
        filtered = filtered.filter(profile__grade=int(grade))
    filtered = _filter_by_area(filtered, region, profile_prefix="profile")
    filtered_count = filtered.count()

    grade_stats = []
    counted = {
        row["profile__grade"]: row["total"]
        for row in filtered.values("profile__grade").annotate(total=Count("id"))
        if row["profile__grade"]
    }
    for number, label in GRADE_CHOICES:
        grade_stats.append(
            {"grade": number, "label": label, "total": counted.get(number, 0)}
        )
    ungraded = filtered.filter(profile__grade__isnull=True).count()

    if request.GET.get("export") == "xlsx":
        rows = []
        for user in filtered:
            profile = user.profile
            joined = timezone.localtime(user.date_joined)
            rows.append(
                [
                    profile.first_name or user.first_name,
                    profile.last_name or user.last_name,
                    profile.phone or "",
                    profile.grade_display,
                    profile.area_label,
                    joined.strftime("%d.%m.%Y %H:%M"),
                ]
            )
        return xlsx_response(
            "istifadeciler.xlsx",
            ["Ad", "Soyad", "Əlaqə", "Sinif", "Ərazi", "Qeydiyyat tarixi"],
            rows,
        )

    return render(
        request,
        "panel/users.html",
        {
            "users": filtered,
            "selected_grade": grade,
            "selected_region": region,
            "grade_choices": GRADE_CHOICES,
            "area_choices": _area_choices(),
            "total_count": total_count,
            "month_count": month_count,
            "filtered_count": filtered_count,
            "filter_active": bool(grade or region),
            "grade_stats": grade_stats,
            "ungraded_count": ungraded,
        },
    )


@staff_required
def site_settings(request):
    settings_obj = SiteSettings.load()
    if request.method == "POST":
        form = SiteSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Sertifikat əlaqə nömrəsi yadda saxlanıldı.")
            return redirect("panel_site_settings")
    else:
        form = SiteSettingsForm(instance=settings_obj)
    return render(request, "panel/site_settings.html", {"form": form})


@staff_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Şifrə yeniləndi.")
            return redirect("panel_dashboard")
    else:
        form = PasswordChangeForm(request.user)
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "field-input")
    return render(request, "panel/password.html", {"form": form})
