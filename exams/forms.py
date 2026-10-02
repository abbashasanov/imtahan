from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from exams.models import Choice, Exam, Question, StudentProfile, Subject


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"


def _aware(value):
    if value and timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


class ExamAdminForm(forms.ModelForm):
    parse_pdf = forms.BooleanField(
        label="PDF-i parse et və sualları bazaya yaz",
        required=False,
        initial=False,
        help_text=(
            "Yeni PDF yüklənəndə suallar avtomatik çıxarılır. "
            "Eyni faylı yenidən parse etmək və ya mövcud sualları əvəz etmək üçün işarələyin."
        ),
    )

    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "duration_minutes",
            "passing_score",
            "opens_at",
            "closes_at",
            "is_active",
            "pdf_file",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["parse_pdf"].label = (
                "PDF-i yenidən parse et (mövcud suallar silinib yenidən yazılacaq)"
            )

    def clean(self):
        cleaned = super().clean()
        parse_pdf = cleaned.get("parse_pdf")
        pdf_file = cleaned.get("pdf_file")
        if parse_pdf and not pdf_file:
            raise forms.ValidationError({"pdf_file": "Parse üçün PDF faylı yüklənməlidir."})
        if parse_pdf and pdf_file:
            name = getattr(pdf_file, "name", "") or ""
            if not name.lower().endswith(".pdf"):
                raise forms.ValidationError({"pdf_file": "Yalnız PDF faylı qəbul edilir."})
        opens_at = cleaned.get("opens_at")
        closes_at = cleaned.get("closes_at")
        if opens_at and closes_at and closes_at <= opens_at:
            raise forms.ValidationError({"closes_at": "Bağlanma tarixi açılma tarixindən sonra olmalıdır."})
        return cleaned


class ExamImportForm(forms.Form):
    title = forms.CharField(label="İmtahanın adı", max_length=255)
    description = forms.CharField(
        label="Təsvir",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    duration_minutes = forms.IntegerField(label="Müddət (dəqiqə)", min_value=1, initial=60)
    passing_score = forms.IntegerField(label="Keçid balı (%)", min_value=0, max_value=100, initial=50)
    opens_at = forms.DateTimeField(label="Açılma tarixi", required=False, widget=DateTimeLocalInput)
    closes_at = forms.DateTimeField(label="Bağlanma tarixi", required=False, widget=DateTimeLocalInput)
    is_active = forms.BooleanField(label="Aktivdir", required=False, initial=True)
    pdf_file = forms.FileField(
        label="PDF faylı",
        help_text="Suallar '1.' / 'Sual 1:' və variantlar 'A)' formatında olmalıdır.",
    )

    def clean_pdf_file(self):
        pdf_file = self.cleaned_data["pdf_file"]
        if not pdf_file.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Yalnız PDF faylı yükləyin.")
        return pdf_file

    def clean(self):
        cleaned = super().clean()
        cleaned["opens_at"] = _aware(cleaned.get("opens_at"))
        cleaned["closes_at"] = _aware(cleaned.get("closes_at"))
        if cleaned.get("opens_at") and cleaned.get("closes_at") and cleaned["closes_at"] <= cleaned["opens_at"]:
            raise forms.ValidationError({"closes_at": "Bağlanma tarixi açılma tarixindən sonra olmalıdır."})
        return cleaned


class PanelExamForm(forms.ModelForm):
    parse_pdf = forms.BooleanField(
        label="PDF-i parse et / yenidən idxal et",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "field-check"}),
    )

    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "grade",
            "duration_minutes",
            "passing_score",
            "opens_at",
            "closes_at",
            "is_active",
            "pdf_file",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "field-input", "placeholder": "Məsələn: 5-ci sinif sınağı"}),
            "description": forms.Textarea(attrs={"class": "field-input", "rows": 3}),
            "grade": forms.Select(attrs={"class": "field-input"}),
            "duration_minutes": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
            "passing_score": forms.NumberInput(attrs={"class": "field-input", "min": 0, "max": 100}),
            "opens_at": DateTimeLocalInput(attrs={"class": "field-input"}, format="%Y-%m-%dT%H:%M"),
            "closes_at": DateTimeLocalInput(attrs={"class": "field-input"}, format="%Y-%m-%dT%H:%M"),
            "is_active": forms.CheckboxInput(attrs={"class": "field-check"}),
            "pdf_file": forms.ClearableFileInput(attrs={"class": "field-input", "accept": "application/pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("opens_at", "closes_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
            self.fields[name].required = False
        self.fields["duration_minutes"].required = False
        self.fields["grade"].required = False
        self.fields["pdf_file"].required = False
        self.fields["pdf_file"].label = "PDF faylı (istəyə bağlı)"
        self.fields["pdf_file"].help_text = (
            "Yükləsəniz suallar avtomatik çıxarılır. "
            "PDF-dən sonra eyni imtahana əl ilə də sual əlavə edə bilərsiniz. "
            "Yenidən idxal mövcud sualları (əl ilə yazılanlar daxil) silər."
        )
        if self.instance.pk:
            self.fields["parse_pdf"].label = (
                "PDF-i yenidən parse et (əl ilə əlavə edilən suallar da silinəcək)"
            )
            for name in ("opens_at", "closes_at"):
                value = getattr(self.instance, name)
                if value:
                    self.initial[name] = timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")

    def clean_opens_at(self):
        return _aware(self.cleaned_data.get("opens_at"))

    def clean_closes_at(self):
        return _aware(self.cleaned_data.get("closes_at"))

    def clean(self):
        cleaned = super().clean()
        opens_at = cleaned.get("opens_at")
        closes_at = cleaned.get("closes_at")
        if opens_at and closes_at and closes_at <= opens_at:
            raise forms.ValidationError({"closes_at": "Bağlanma tarixi açılma tarixindən sonra olmalıdır."})
        parse_pdf = cleaned.get("parse_pdf")
        pdf_file = cleaned.get("pdf_file")
        if parse_pdf and not pdf_file:
            raise forms.ValidationError({"pdf_file": "Parse üçün PDF faylı seçin."})
        return cleaned


class PhoneDistrictMixin:
    def clean_phone(self):
        from exams.phone import normalize_phone

        raw = (self.cleaned_data.get("phone") or "").strip()
        if not raw:
            raise forms.ValidationError("Əlaqə nömrəsi mütləqdir.")
        try:
            return normalize_phone(raw)
        except ValueError:
            raise forms.ValidationError(
                "Düzgün Azərbaycan mobil nömrəsi yazın. Nümunə: 050 111 22 33"
            )

    def _region_choices(self):
        from exams.regions import REGION_GROUPS

        choices = [("", "Şəhər / bölgə seçin")]
        for label, names in REGION_GROUPS:
            choices.append((label, [(name, name) for name in names]))
        return choices

    def _baku_choices(self):
        from exams.regions import BAKU_DISTRICT_CHOICES

        return [("", "Rayonu seçin")] + list(BAKU_DISTRICT_CHOICES)

    def _grade_choices(self):
        from exams.regions import GRADE_CHOICES

        return [("", "Sinifi seçin")] + list(GRADE_CHOICES)

    def clean(self):
        from exams.regions import BAKU, BAKU_DISTRICT_VALUES, REGION_VALUES

        cleaned = super().clean()
        region = cleaned.get("region")
        if region and region not in REGION_VALUES:
            self.add_error("region", "Siyahıdan şəhər və ya bölgə seçin.")
            return cleaned
        if region == BAKU:
            district = cleaned.get("baku_district")
            if district not in BAKU_DISTRICT_VALUES:
                self.add_error("baku_district", "Bakı şəhəri üçün rayonu seçin.")
            cleaned["address"] = ""
        elif region:
            if not (cleaned.get("address") or "").strip():
                self.add_error("address", "Bakıdan kənar üçün ünvanı yazın.")
            cleaned["baku_district"] = ""
        return cleaned


class StudentRegistrationForm(PhoneDistrictMixin, forms.Form):
    username = forms.CharField(label="İstifadəçi adı", max_length=150)
    first_name = forms.CharField(label="Ad", max_length=80)
    last_name = forms.CharField(label="Soyad", max_length=80)
    phone = forms.CharField(
        label="Əlaqə nömrəsi",
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "050 111 22 33"}),
    )
    grade = forms.ChoiceField(label="Sinif")
    region = forms.ChoiceField(label="Şəhər / bölgə")
    baku_district = forms.ChoiceField(label="Bakı rayonu", required=False)
    address = forms.CharField(label="Ünvan", required=False, max_length=255)
    password1 = forms.CharField(
        label="Şifrə",
        min_length=4,
        widget=forms.PasswordInput,
        help_text="Ən azı 4 simvol. İstənilən şifrə ola bilər.",
    )
    password2 = forms.CharField(label="Şifrənin təkrarı", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grade"].choices = self._grade_choices()
        self.fields["region"].choices = self._region_choices()
        self.fields["baku_district"].choices = self._baku_choices()
        for name, field in self.fields.items():
            field.required = name not in {"baku_district", "address"}

    def clean_username(self):
        from django.contrib.auth import get_user_model

        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu istifadəçi adı artıq mövcuddur.")
        return username

    def clean_password1(self):
        password = self.cleaned_data.get("password1") or ""
        if len(password) < 4:
            raise forms.ValidationError("Şifrə ən azı 4 simvol olmalıdır.")
        return password

    def clean_grade(self):
        value = self.cleaned_data.get("grade")
        if not value:
            raise forms.ValidationError("Sinifi seçin.")
        return int(value)

    def clean_phone(self):
        phone = super().clean_phone()
        from exams.models import StudentProfile

        if StudentProfile.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Bu əlaqə nömrəsi ilə artıq qeydiyyat var.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") and cleaned.get("password2") and cleaned["password1"] != cleaned["password2"]:
            self.add_error("password2", "Şifrələr eyni deyil.")
        return cleaned

    def save(self):
        from django.contrib.auth import get_user_model

        from exams.models import StudentProfile

        user = get_user_model().objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data["last_name"].strip(),
        )
        StudentProfile.objects.create(
            user=user,
            phone=self.cleaned_data["phone"],
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data["last_name"].strip(),
            grade=self.cleaned_data["grade"],
            region=self.cleaned_data["region"],
            baku_district=self.cleaned_data.get("baku_district") or "",
            address=(self.cleaned_data.get("address") or "").strip(),
        )
        return user


class StudentProfileForm(PhoneDistrictMixin, forms.Form):
    first_name = forms.CharField(label="Ad", max_length=80)
    last_name = forms.CharField(label="Soyad", max_length=80)
    phone = forms.CharField(
        label="Əlaqə nömrəsi",
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "050 111 22 33"}),
    )
    grade = forms.ChoiceField(label="Sinif")
    region = forms.ChoiceField(label="Şəhər / bölgə")
    baku_district = forms.ChoiceField(label="Bakı rayonu", required=False)
    address = forms.CharField(label="Ünvan", required=False, max_length=255)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["grade"].choices = self._grade_choices()
        self.fields["region"].choices = self._region_choices()
        self.fields["baku_district"].choices = self._baku_choices()
        profile = StudentProfile.objects.filter(user=user).first()
        if profile and not self.is_bound:
            self.fields["phone"].initial = profile.phone
            self.fields["first_name"].initial = profile.first_name or user.first_name
            self.fields["last_name"].initial = profile.last_name or user.last_name
            self.fields["grade"].initial = profile.grade
            self.fields["region"].initial = profile.region
            self.fields["baku_district"].initial = profile.baku_district
            self.fields["address"].initial = profile.address

    def clean_grade(self):
        value = self.cleaned_data.get("grade")
        if not value:
            raise forms.ValidationError("Sinifi seçin.")
        return int(value)

    def clean_phone(self):
        phone = super().clean_phone()
        from exams.models import StudentProfile

        if StudentProfile.objects.filter(phone=phone).exclude(user=self.user).exists():
            raise forms.ValidationError("Bu əlaqə nömrəsi ilə artıq qeydiyyat var.")
        return phone

    def save(self):
        from exams.models import StudentProfile

        first_name = self.cleaned_data["first_name"].strip()
        last_name = self.cleaned_data["last_name"].strip()
        self.user.first_name = first_name
        self.user.last_name = last_name
        self.user.save(update_fields=["first_name", "last_name"])
        profile, _created = StudentProfile.objects.update_or_create(
            user=self.user,
            defaults={
                "phone": self.cleaned_data["phone"],
                "first_name": first_name,
                "last_name": last_name,
                "grade": self.cleaned_data["grade"],
                "region": self.cleaned_data["region"],
                "baku_district": self.cleaned_data.get("baku_district") or "",
                "address": (self.cleaned_data.get("address") or "").strip(),
            },
        )
        return profile


class QuestionEditForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["number", "text", "points", "subject", "image"]
        widgets = {
            "number": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
            "text": forms.Textarea(attrs={"class": "field-input", "rows": 5}),
            "points": forms.NumberInput(attrs={"class": "field-input", "min": 0, "placeholder": "Boş = ümumi tənzimləmə"}),
            "subject": forms.Select(attrs={"class": "field-input"}),
            "image": forms.ClearableFileInput(attrs={"class": "field-input", "accept": "image/*"}),
        }

    def clean_number(self):
        number = self.cleaned_data["number"]
        exam = self.instance.exam_id
        if not exam:
            return number
        clash = Question.objects.filter(exam_id=exam, number=number)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("Bu sual nömrəsi artıq mövcuddur.")
        return number

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["points"].required = False
        self.fields["subject"].required = False
        self.fields["subject"].queryset = Subject.objects.all()
        self.fields["subject"].empty_label = "— fənn seçin —"


class ChoiceEditForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ["letter", "text", "image", "is_correct"]
        widgets = {
            "letter": forms.Select(attrs={"class": "field-input"}),
            "text": forms.Textarea(attrs={"class": "field-input", "rows": 2}),
            "image": forms.ClearableFileInput(attrs={"class": "field-input", "accept": "image/*"}),
            "is_correct": forms.CheckboxInput(attrs={"class": "field-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["letter"].choices = [("", "Hərf")] + list(Choice.LETTERS)
        self.fields["letter"].required = False
        self.fields["text"].required = False

    def clean(self):
        cleaned = super().clean()
        letter = cleaned.get("letter")
        text = (cleaned.get("text") or "").strip()
        image = cleaned.get("image")
        is_correct = cleaned.get("is_correct")
        has_content = bool(text or image or is_correct)
        if has_content and not letter:
            self.add_error("letter", "Variantın hərfini seçin.")
        if not has_content:
            self.cleaned_data["DELETE"] = True
        return cleaned


QuestionChoiceFormSet = inlineformset_factory(
    Question,
    Choice,
    form=ChoiceEditForm,
    extra=1,
    max_num=5,
    can_delete=True,
)

QuestionChoiceCreateFormSet = inlineformset_factory(
    Question,
    Choice,
    form=ChoiceEditForm,
    extra=5,
    max_num=5,
    can_delete=True,
)


class ExamSettingsForm(forms.ModelForm):
    unlimited_time = forms.BooleanField(
        label="Vaxt qoyulmasın",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "field-check"}),
    )

    class Meta:
        model = Exam
        fields = [
            "grade",
            "default_points",
            "duration_minutes",
            "access_mode",
            "max_attempts",
            "passing_score",
            "shuffle_questions",
            "shuffle_choices",
            "show_score_immediately",
            "show_correct_answers",
        ]
        widgets = {
            "grade": forms.Select(attrs={"class": "field-input"}),
            "default_points": forms.NumberInput(attrs={"class": "field-input", "min": 0, "placeholder": "Məsələn: 10"}),
            "duration_minutes": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
            "access_mode": forms.Select(attrs={"class": "field-input"}),
            "max_attempts": forms.NumberInput(attrs={"class": "field-input", "min": 1}),
            "passing_score": forms.NumberInput(attrs={"class": "field-input", "min": 0, "max": 100}),
            "shuffle_questions": forms.CheckboxInput(attrs={"class": "field-check"}),
            "shuffle_choices": forms.CheckboxInput(attrs={"class": "field-check"}),
            "show_score_immediately": forms.CheckboxInput(attrs={"class": "field-check"}),
            "show_correct_answers": forms.CheckboxInput(attrs={"class": "field-check"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_points"].required = False
        self.fields["duration_minutes"].required = False
        self.fields["grade"].required = False
        self.fields["grade"].empty_label = "Qarışıq / təyin olunmayıb"
        if self.instance.pk and not self.instance.duration_minutes:
            self.fields["unlimited_time"].initial = True

    def clean_default_points(self):
        value = self.cleaned_data.get("default_points")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("unlimited_time"):
            cleaned["duration_minutes"] = None
        elif not cleaned.get("duration_minutes"):
            self.add_error(
                "duration_minutes",
                "Müddəti yazın və ya «Vaxt qoyulmasın» seçin.",
            )
        max_attempts = cleaned.get("max_attempts")
        if max_attempts is not None and max_attempts < 1:
            self.add_error("max_attempts", "Ən azı 1 cəhd olmalıdır.")
        return cleaned
