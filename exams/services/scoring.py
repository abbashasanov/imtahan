"""İmtahan balının hesablanması, fənn statistikası və sual xəbərdarlıqları."""

from __future__ import annotations

from collections import OrderedDict

from django.db.models import Q


def has_correct_answer(question) -> bool:
    choices = getattr(question, "choices", None)
    if choices is None:
        return False
    return any(choice.is_correct for choice in question.choices.all())


def correct_letter(question) -> str:
    for choice in question.choices.all():
        if choice.is_correct:
            return choice.letter
    return ""


def effective_points(question) -> int | None:
    """Sualın öz balı varsa o, yoxdursa imtahanın ümumi balı."""
    if question.points is not None:
        return int(question.points)
    default = getattr(question.exam, "default_points", None)
    if default is not None:
        return int(default)
    return None


def question_warnings(question) -> list[str]:
    warnings = []
    if not has_correct_answer(question):
        warnings.append("Düzgün cavab təyin edilməyib.")
    if effective_points(question) is None:
        warnings.append("Bal təyin edilməyib (nə sualda, nə ümumi tənzimləmədə).")
    if not question.subject_id:
        warnings.append("Fənn təyin edilməyib.")
    return warnings


def score_answers(questions, answers_by_question_id: dict) -> tuple[int, int, float]:
    """Düzgün cavablara görə (qazanılan, maksimum, faiz) qaytarır."""
    earned = 0
    maximum = 0
    for question in questions:
        points = effective_points(question) or 0
        maximum += points
        choice = answers_by_question_id.get(question.pk)
        if choice is not None and getattr(choice, "is_correct", False):
            earned += points
    percent = round((earned / maximum) * 100, 2) if maximum else 0.0
    return earned, maximum, percent


def subject_results(questions, answers_by_question_id: dict) -> list[dict]:
    """Hər fənn üçün doğru/səhv/boş, bal və hərf zəncirləri."""
    groups: OrderedDict[int | str, dict] = OrderedDict()
    for question in questions:
        subject = getattr(question, "subject", None)
        key = subject.pk if subject is not None else "none"
        if key not in groups:
            groups[key] = {
                "subject": subject,
                "name": subject.name if subject is not None else "Fənn təyin edilməyib",
                "correct": 0,
                "wrong": 0,
                "blank": 0,
                "total": 0,
                "earned": 0,
                "max_points": 0,
                "student_answers": [],
                "correct_answers": [],
            }
        row = groups[key]
        points = effective_points(question) or 0
        right = correct_letter(question)
        row["total"] += 1
        row["max_points"] += points
        row["correct_answers"].append(right or "-")
        choice = answers_by_question_id.get(question.pk)
        if choice is None:
            row["blank"] += 1
            row["student_answers"].append("-")
        else:
            letter = choice.letter
            row["student_answers"].append(letter)
            if getattr(choice, "is_correct", False):
                row["correct"] += 1
                row["earned"] += points
            else:
                row["wrong"] += 1
    result = []
    for row in groups.values():
        row["student_key"] = "".join(row["student_answers"])
        row["correct_key"] = "".join(row["correct_answers"])
        result.append(row)
    return result


def answers_map(submission) -> dict:
    return {
        answer.question_id: answer.choice
        for answer in submission.answers.select_related("choice")
    }


def submission_rank(submission) -> int:
    from exams.models import ExamSubmission

    better = ExamSubmission.objects.filter(exam=submission.exam, is_completed=True).filter(
        Q(earned_points__gt=submission.earned_points)
        | Q(
            earned_points=submission.earned_points,
            submitted_at__lt=submission.submitted_at,
        )
        | Q(
            earned_points=submission.earned_points,
            submitted_at=submission.submitted_at,
            pk__lt=submission.pk,
        )
    )
    if submission.submitted_at is None:
        better = ExamSubmission.objects.filter(
            exam=submission.exam, is_completed=True, earned_points__gt=submission.earned_points
        )
    return better.count() + 1


def ranked_submissions(queryset):
    items = list(queryset)
    items.sort(
        key=lambda item: (
            -(item.earned_points or 0),
            item.submitted_at or item.started_at,
            item.pk,
        )
    )
    for index, item in enumerate(items, start=1):
        item.rank = index
    return items


def answer_sheet_payload(submission) -> dict:
    exam = submission.exam
    questions = list(
        exam.questions.select_related("subject", "exam").prefetch_related("choices")
    )
    mapping = answers_map(submission)
    profile = getattr(submission.user, "profile", None)
    return {
        "submission": submission,
        "profile": profile,
        "rank": submission_rank(submission),
        "subjects": subject_results(questions, mapping),
        "earned_points": submission.earned_points,
        "max_points": submission.max_points,
    }
