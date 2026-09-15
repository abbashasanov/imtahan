from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from exams.forms import ExamAdminForm, ExamImportForm
from exams.models import Certificate, Choice, Exam, ExamSubmission, Question, StudentProfile, Subject, UserAnswer
from exams.services.pdf_parser import ParseError, import_exam_from_pdf


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ("letter", "text", "image", "is_correct")


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("number", "text", "subject", "image")
    show_change_link = True
    readonly_fields = ()


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    form = ExamAdminForm
    list_display = (
        "title",
        "opens_at",
        "closes_at",
        "is_active",
        "question_count_display",
        "created_at",
        "import_link",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "description")
    inlines = [QuestionInline]
    readonly_fields = ("created_at",)
    fieldsets = (
        (
            "İmtahan məlumatı",
            {"fields": ("title", "description", "grade", "duration_minutes", "passing_score", "opens_at", "closes_at", "is_active", "created_at")},
        ),
        (
            "PDF-dən avtomatik idxal",
            {
                "fields": ("pdf_file", "parse_pdf"),
                "description": (
                    "PDF yükləyin. Suallar '1.', '1)' və ya 'Sual 1:' formatında, "
                    "variantlar isə A) B) C) D) E) şəklində tanınır."
                ),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-pdf/",
                self.admin_site.admin_view(self.import_pdf_view),
                name="exams_exam_import_pdf",
            ),
        ]
        return custom + urls

    @admin.display(description="Sual sayı")
    def question_count_display(self, obj):
        return obj.question_count

    @admin.display(description="PDF idxalı")
    def import_link(self, obj):
        url = reverse("admin:exams_exam_import_pdf")
        return format_html('<a class="button" href="{}">PDF yüklə</a>', url)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_pdf_url"] = reverse("admin:exams_exam_import_pdf")
        return super().changelist_view(request, extra_context=extra_context)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        pdf_changed = "pdf_file" in form.changed_data and bool(obj.pdf_file)
        parse_pdf = form.cleaned_data.get("parse_pdf") or pdf_changed

        try:
            if parse_pdf and obj.pdf_file:
                result = import_exam_from_pdf(obj, obj.pdf_file)
                self.message_user(
                    request,
                    (
                        f"{result['questions']} sual və {result['choices']} variant yazıldı. "
                        "Düzgün cavabları imtahan səhifəsindən təyin edin."
                    ),
                    level=messages.SUCCESS,
                )
        except ParseError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)

    def import_pdf_view(self, request):
        if request.method == "POST":
            form = ExamImportForm(request.POST, request.FILES)
            if form.is_valid():
                exam = Exam(
                    title=form.cleaned_data["title"],
                    description=form.cleaned_data["description"],
                    duration_minutes=form.cleaned_data["duration_minutes"],
                    passing_score=form.cleaned_data.get("passing_score") or 50,
                    opens_at=form.cleaned_data.get("opens_at"),
                    closes_at=form.cleaned_data.get("closes_at"),
                    is_active=form.cleaned_data["is_active"],
                    pdf_file=form.cleaned_data["pdf_file"],
                )
                try:
                    exam.save()
                    result = import_exam_from_pdf(exam, exam.pdf_file)
                    self.message_user(
                        request,
                        (
                            f"«{exam.title}» yaradıldı: {result['questions']} sual, "
                            f"{result['choices']} variant. "
                            "Düzgün cavabları imtahan səhifəsindən təyin edin."
                        ),
                        level=messages.SUCCESS,
                    )
                    return redirect("admin:exams_exam_change", exam.pk)
                except ParseError as exc:
                    exam.delete()
                    form.add_error("pdf_file", str(exc))
        else:
            form = ExamImportForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "PDF-dən imtahan idxal et",
        }
        return render(request, "admin/exams/exam/import_pdf.html", context)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    ordering = ("order", "name")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("number", "exam", "subject", "short_text")
    list_filter = ("exam", "subject")
    search_fields = ("text",)
    inlines = [ChoiceInline]

    @admin.display(description="Sual")
    def short_text(self, obj):
        return obj.text[:80]


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("letter", "question", "is_correct", "short_text")
    list_filter = ("is_correct", "letter", "question__exam")
    search_fields = ("text",)

    @admin.display(description="Mətn")
    def short_text(self, obj):
        return obj.text[:80]


class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ("question", "choice")
    can_delete = False


@admin.register(ExamSubmission)
class ExamSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "exam", "score", "is_completed", "submitted_at")
    list_filter = ("is_completed", "exam")
    search_fields = ("user__username", "exam__title")
    readonly_fields = (
        "user",
        "exam",
        "started_at",
        "submitted_at",
        "score",
        "is_completed",
    )
    inlines = [UserAnswerInline]


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("code", "student_name", "exam_title", "issued_at")
    search_fields = ("code", "submission__user__username", "submission__exam__title")
    readonly_fields = ("code", "submission", "issued_at")

    @admin.display(description="Tələbə")
    def student_name(self, obj):
        return obj.student_name

    @admin.display(description="İmtahan")
    def exam_title(self, obj):
        return obj.submission.exam.title


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "phone", "grade", "area_label", "code")
    search_fields = ("user__username", "first_name", "last_name", "phone", "region", "address", "code")
    list_filter = ("grade", "region", "baku_district")

    @admin.display(description="Ad Soyad")
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description="Ərazi")
    def area_label(self, obj):
        return obj.area_label


admin.site.site_header = "İmtahan platforması"
admin.site.site_title = "İmtahan admin"
admin.site.index_title = "İdarə paneli"
