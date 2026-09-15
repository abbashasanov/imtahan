from django.conf import settings
from django.db import models
from django.utils import timezone

from exams.regions import (
    BAKU,
    BAKU_DISTRICT_CHOICES,
    GRADE_CHOICES,
    REGION_CHOICES,
    grade_label,
)


class Exam(models.Model):
    STATUS_OPEN = "aciq"
    STATUS_SCHEDULED = "gozleyir"
    STATUS_CLOSED = "baglanib"
    STATUS_INACTIVE = "deaktiv"
    STATUS_LABELS = {
        STATUS_OPEN: "Açıqdır",
        STATUS_SCHEDULED: "Tezliklə açılacaq",
        STATUS_CLOSED: "Bağlanıb",
        STATUS_INACTIVE: "Deaktiv",
    }

    ACCESS_REGISTERED = "registered"
    ACCESS_PUBLIC = "public"
    ACCESS_CHOICES = [
        (ACCESS_REGISTERED, "Yalnız qeydiyyatlı istifadəçilər"),
        (ACCESS_PUBLIC, "İstənilən adam baxa bilər"),
    ]

    title = models.CharField("Ad", max_length=255)
    description = models.TextField("Təsvir", blank=True)
    grade = models.PositiveSmallIntegerField(
        "Sinif",
        choices=GRADE_CHOICES,
        blank=True,
        null=True,
        help_text="Məsələn 5-ci sinif imtahanı. Boş buraxılsa qarışıq ola bilər.",
    )
    duration_minutes = models.PositiveIntegerField(
        "Müddət (dəqiqə)",
        blank=True,
        null=True,
        default=60,
        help_text="Boş buraxılsa vaxt limiti olmur.",
    )
    passing_score = models.PositiveIntegerField("Keçid balı (%)", default=50)
    default_points = models.PositiveIntegerField(
        "Hər sualın ümumi balı",
        blank=True,
        null=True,
        default=1,
        help_text="Sualın öz balı yoxdursa bu dəyər istifadə olunur.",
    )
    access_mode = models.CharField(
        "Kim baxa bilər",
        max_length=20,
        choices=ACCESS_CHOICES,
        default=ACCESS_REGISTERED,
    )
    shuffle_questions = models.BooleanField("Sualları qarışdır", default=False)
    shuffle_choices = models.BooleanField("Variantları qarışdır", default=False)
    max_attempts = models.PositiveIntegerField("Cəhd sayı", default=1)
    show_score_immediately = models.BooleanField("Nəticəni dərhal göstər", default=True)
    show_correct_answers = models.BooleanField("Təhvildən sonra düzgün cavabları göstər", default=True)
    opens_at = models.DateTimeField("Açılma tarixi", blank=True, null=True)
    closes_at = models.DateTimeField("Bağlanma tarixi", blank=True, null=True)
    created_at = models.DateTimeField("Yaradılma tarixi", auto_now_add=True)
    is_active = models.BooleanField("Aktivdir", default=True)
    pdf_file = models.FileField(
        "PDF faylı",
        upload_to="exams/pdfs/",
        blank=True,
        null=True,
        help_text="Sınaq suallarının olduğu PDF. Yüklənəndə suallar avtomatik parse edilə bilər.",
    )

    class Meta:
        verbose_name = "İmtahan"
        verbose_name_plural = "İmtahanlar"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def question_count(self):
        return self.questions.count()

    def availability_status(self):
        now = timezone.now()
        if not self.is_active:
            return self.STATUS_INACTIVE
        if self.opens_at and now < self.opens_at:
            return self.STATUS_SCHEDULED
        if self.closes_at and now > self.closes_at:
            return self.STATUS_CLOSED
        return self.STATUS_OPEN

    def availability_label(self):
        return self.STATUS_LABELS[self.availability_status()]

    def is_available(self):
        return self.availability_status() == self.STATUS_OPEN

    def has_time_limit(self):
        return bool(self.duration_minutes)

    def grade_display(self):
        return grade_label(self.grade) if self.grade else ""


class Subject(models.Model):
    name = models.CharField("Ad", max_length=80, unique=True)
    order = models.PositiveSmallIntegerField("Sıra", default=0)

    class Meta:
        verbose_name = "Fənn"
        verbose_name_plural = "Fənlər"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="İstifadəçi",
    )
    phone = models.CharField("Əlaqə nömrəsi", max_length=16, unique=True)
    first_name = models.CharField("Ad", max_length=80, blank=True)
    last_name = models.CharField("Soyad", max_length=80, blank=True)
    grade = models.PositiveSmallIntegerField("Sinif", choices=GRADE_CHOICES, blank=True, null=True)
    region = models.CharField("Şəhər / bölgə", max_length=64, choices=REGION_CHOICES, blank=True)
    baku_district = models.CharField(
        "Bakı rayonu",
        max_length=64,
        choices=BAKU_DISTRICT_CHOICES,
        blank=True,
    )
    address = models.CharField("Ünvan", max_length=255, blank=True)
    code = models.CharField("İş nömrəsi", max_length=16, unique=True, blank=True, null=True)

    class Meta:
        verbose_name = "Tələbə profili"
        verbose_name_plural = "Tələbə profilləri"

    def __str__(self):
        return f"{self.full_name} — {self.phone}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code and self.user_id:
            self.code = str(10000 + self.user_id)
            super().save(update_fields=["code"])

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        if name:
            return name
        user = getattr(self, "user", None)
        if user:
            full = user.get_full_name().strip()
            return full or user.get_username()
        return ""

    @property
    def grade_display(self):
        return grade_label(self.grade) if self.grade else "—"

    @property
    def area_label(self):
        if self.region == BAKU and self.baku_district:
            return f"{BAKU} — {self.baku_district}"
        if self.region and self.address:
            return f"{self.region} · {self.address}"
        return self.region or self.address or "—"

    def is_complete(self) -> bool:
        if not (self.phone and self.first_name and self.last_name and self.grade and self.region):
            return False
        if self.region == BAKU:
            return bool(self.baku_district)
        return bool(self.address)


def profile_is_complete(user) -> bool:
    profile = StudentProfile.objects.filter(user_id=user.pk).first()
    return bool(profile and profile.is_complete())


class Question(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="İmtahan",
    )
    number = models.PositiveIntegerField("Sual nömrəsi")
    text = models.TextField("Sual mətni")
    image = models.ImageField(
        "Sual şəkli",
        upload_to="exams/questions/",
        blank=True,
        null=True,
        help_text="Düstur, qrafik və ya cədvəl kəsildikdə buraya yükləyin.",
    )
    points = models.PositiveIntegerField(
        "Sual balı",
        blank=True,
        null=True,
        help_text="Boşdursa imtahanın ümumi tənzimləməsindəki bal götürülür.",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        related_name="questions",
        verbose_name="Fənn",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Sual"
        verbose_name_plural = "Suallar"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["exam", "number"], name="unique_exam_question_number"),
        ]

    def __str__(self):
        return f"{self.exam.title} — {self.number}"


class Choice(models.Model):
    LETTERS = [(letter, letter) for letter in "ABCDE"]

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices",
        verbose_name="Sual",
    )
    letter = models.CharField("Hərf", max_length=1, choices=LETTERS)
    text = models.TextField("Variant mətni", blank=True)
    image = models.ImageField(
        "Variant şəkli",
        upload_to="exams/choices/",
        blank=True,
        null=True,
    )
    is_correct = models.BooleanField("Düzgün cavab", default=False)

    class Meta:
        verbose_name = "Variant"
        verbose_name_plural = "Variantlar"
        ordering = ["letter"]
        constraints = [
            models.UniqueConstraint(fields=["question", "letter"], name="unique_question_choice_letter"),
        ]

    def __str__(self):
        return f"{self.question.number}{self.letter}"


class ExamSubmission(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exam_submissions",
        verbose_name="Tələbə",
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="İmtahan",
    )
    started_at = models.DateTimeField("Başlama vaxtı", auto_now_add=True)
    submitted_at = models.DateTimeField("Təhvil vaxtı", blank=True, null=True)
    score = models.DecimalField("Yekun bal", max_digits=6, decimal_places=2, default=0)
    earned_points = models.PositiveIntegerField("Qazanılan bal", default=0)
    max_points = models.PositiveIntegerField("Maksimum bal", default=0)
    is_completed = models.BooleanField("Tamamlanıb", default=False)

    class Meta:
        verbose_name = "İmtahan nəticəsi"
        verbose_name_plural = "İmtahan nəticələri"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "exam"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.exam}"

    @property
    def correct_count(self):
        return self.answers.filter(choice__is_correct=True).count()

    @property
    def passed(self):
        return self.is_completed and self.score >= self.exam.passing_score


class UserAnswer(models.Model):
    submission = models.ForeignKey(
        ExamSubmission,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="Nəticə",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="user_answers",
        verbose_name="Sual",
    )
    choice = models.ForeignKey(
        Choice,
        on_delete=models.SET_NULL,
        related_name="user_answers",
        verbose_name="Seçilmiş variant",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Tələbə cavabı"
        verbose_name_plural = "Tələbə cavabları"
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "question"],
                name="unique_submission_question_answer",
            ),
        ]

    def __str__(self):
        selected = self.choice.letter if self.choice else "—"
        return f"{self.submission.user} / {self.question.number}: {selected}"


class Certificate(models.Model):
    submission = models.OneToOneField(
        ExamSubmission,
        on_delete=models.CASCADE,
        related_name="certificate",
        verbose_name="Nəticə",
    )
    code = models.CharField("Sertifikat kodu", max_length=32, unique=True)
    issued_at = models.DateTimeField("Verilmə tarixi", auto_now_add=True)

    class Meta:
        verbose_name = "Sertifikat"
        verbose_name_plural = "Sertifikatlar"
        ordering = ["-issued_at"]

    def __str__(self):
        return self.code

    @property
    def student_name(self):
        user = self.submission.user
        profile = getattr(user, "profile", None)
        if profile and profile.full_name:
            return profile.full_name
        full = user.get_full_name().strip()
        return full or user.get_username()
