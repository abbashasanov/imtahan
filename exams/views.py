import random

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from exams.forms import StudentProfileForm, StudentRegistrationForm
from exams.models import Certificate, Exam, ExamSubmission, UserAnswer, profile_is_complete
from exams.services.certificates import build_certificate_pdf, issue_certificate_if_passed
from exams.services.scoring import answer_sheet_payload, score_answers


def _safe_next(request, default="exam_list"):
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return candidate
    return default


def register(request):
    if request.user.is_authenticated:
        return redirect("exam_list")
    if request.method == "POST":
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Qeydiyyat tamamlandı. İmtahana başlaya bilərsiniz.")
            return redirect("exam_list")
    else:
        form = StudentRegistrationForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def complete_profile(request):
    if request.method == "POST":
        form = StudentProfileForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil məlumatı yadda saxlanıldı.")
            return redirect(_safe_next(request))
    else:
        form = StudentProfileForm(request.user)
    return render(
        request,
        "registration/complete_profile.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


@login_required
def post_login(request):
    if request.user.is_staff:
        return redirect("panel_dashboard")
    if not profile_is_complete(request.user):
        return redirect("complete_profile")
    return redirect("exam_list")


def exam_list(request):
    exams = Exam.objects.filter(is_active=True).prefetch_related("questions")
    if not request.user.is_authenticated:
        exams = exams.filter(access_mode=Exam.ACCESS_PUBLIC)
    submissions = {}
    if request.user.is_authenticated:
        latest = (
            ExamSubmission.objects.filter(user=request.user, is_completed=True)
            .order_by("exam_id", "-submitted_at")
        )
        for item in latest:
            submissions.setdefault(item.exam_id, item)
    for exam in exams:
        exam.user_submission = submissions.get(exam.pk)
        exam.completed_attempts = 0
    if request.user.is_authenticated:
        from django.db.models import Count

        counts = (
            ExamSubmission.objects.filter(user=request.user, is_completed=True)
            .values("exam_id")
            .annotate(total=Count("id"))
        )
        by_exam = {row["exam_id"]: row["total"] for row in counts}
        for exam in exams:
            exam.completed_attempts = by_exam.get(exam.pk, 0)
    return render(request, "exams/exam_list.html", {"exams": exams})


@login_required
def take_exam(request, pk):
    exam = get_object_or_404(Exam, pk=pk, is_active=True)
    incomplete = ExamSubmission.objects.filter(
        user=request.user, exam=exam, is_completed=False
    ).first()
    completed_qs = ExamSubmission.objects.filter(user=request.user, exam=exam, is_completed=True)
    latest_completed = completed_qs.order_by("-submitted_at").first()
    if incomplete is None and latest_completed and completed_qs.count() >= exam.max_attempts:
        return redirect("exam_result", pk=latest_completed.pk)

    if not request.user.is_staff and not profile_is_complete(request.user):
        messages.warning(
            request,
            "İmtahanda iştirak üçün ad, soyad, sinif, əlaqə nömrəsi və yaşayış yeri mütləqdir.",
        )
        return redirect(
            f"{reverse('complete_profile')}?next={reverse('take_exam', args=[exam.pk])}"
        )

    if not exam.is_available():
        messages.warning(
            request,
            f"Bu imtahan hazırda açıq deyil ({exam.availability_label()}).",
        )
        return redirect("exam_list")

    question_qs = exam.questions.prefetch_related("choices")

    if request.method == "POST":
        with transaction.atomic():
            submission = incomplete or ExamSubmission.objects.create(user=request.user, exam=exam)
            if submission.is_completed:
                return redirect("exam_result", pk=submission.pk)

            answers_by_id = {}
            for question in question_qs:
                raw_id = request.POST.get(f"q_{question.pk}")
                choice = None
                if raw_id:
                    choice = question.choices.filter(pk=raw_id).first()
                UserAnswer.objects.update_or_create(
                    submission=submission,
                    question=question,
                    defaults={"choice": choice},
                )
                answers_by_id[question.pk] = choice

            earned, maximum, percent = score_answers(question_qs, answers_by_id)
            submission.earned_points = earned
            submission.max_points = maximum
            submission.score = percent
            submission.is_completed = True
            submission.submitted_at = timezone.now()
            submission.save(
                update_fields=["earned_points", "max_points", "score", "is_completed", "submitted_at"]
            )
            issue_certificate_if_passed(submission)
        return redirect("exam_result", pk=submission.pk)

    submission = incomplete
    if submission is None:
        submission = ExamSubmission.objects.create(user=request.user, exam=exam)

    questions = list(question_qs)
    rng = random.Random(submission.pk)
    if exam.shuffle_questions:
        rng.shuffle(questions)
    for question in questions:
        choices = list(question.choices.all())
        if exam.shuffle_choices:
            rng.shuffle(choices)
        question.display_choices = choices

    return render(
        request,
        "exams/take_exam.html",
        {
            "exam": exam,
            "questions": questions,
            "submission": submission,
        },
    )


@login_required
def exam_result(request, pk):
    submission = get_object_or_404(
        ExamSubmission.objects.select_related("exam", "user", "user__profile"),
        pk=pk,
        user=request.user,
        is_completed=True,
    )
    payload = answer_sheet_payload(submission)
    certificate = Certificate.objects.filter(submission=submission).first()
    return render(
        request,
        "exams/exam_result.html",
        {
            **payload,
            "certificate": certificate,
            "show_score": submission.exam.show_score_immediately or request.user.is_staff,
            "show_answers": submission.exam.show_correct_answers or request.user.is_staff,
            "staff_view": False,
        },
    )


@login_required
def certificate_pdf(request, pk):
    certificate = get_object_or_404(
        Certificate.objects.select_related("submission__user", "submission__exam"),
        pk=pk,
    )
    is_owner = certificate.submission.user_id == request.user.id
    if not (request.user.is_staff or is_owner):
        return HttpResponseForbidden("Bu sertifikata baxmaq icazəniz yoxdur.")
    response = HttpResponse(build_certificate_pdf(certificate), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{certificate.code}.pdf"'
    return response
