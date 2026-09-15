from django.db import migrations, models
import django.db.models.deletion


DEFAULT_SUBJECTS = (
    "Azərbaycan dili",
    "Riyaziyyat",
    "İngilis dili",
    "Rus dili",
    "Həyat bilgisi",
    "Məntiq",
)


def seed_subjects(apps, schema_editor):
    Subject = apps.get_model("exams", "Subject")
    for index, name in enumerate(DEFAULT_SUBJECTS, start=1):
        Subject.objects.get_or_create(name=name, defaults={"order": index})


def migrate_profiles(apps, schema_editor):
    StudentProfile = apps.get_model("exams", "StudentProfile")
    for profile in StudentProfile.objects.all():
        district = (profile.district or "").strip()
        if district.startswith("Bakı — "):
            profile.region = "Bakı"
            profile.baku_district = district.removeprefix("Bakı — ").strip()
            profile.address = ""
        elif district.startswith("Bakı - "):
            profile.region = "Bakı"
            profile.baku_district = district.removeprefix("Bakı - ").strip()
            profile.address = ""
        else:
            profile.region = district
            profile.baku_district = ""
        if not profile.grade:
            profile.grade = 1
        if not profile.code and profile.user_id:
            profile.code = str(10000 + profile.user_id)
        profile.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0005_unmark_imported_correct_answers"),
    ]

    operations = [
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True, verbose_name="Ad")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
            ],
            options={
                "verbose_name": "Fənn",
                "verbose_name_plural": "Fənlər",
                "ordering": ["order", "name"],
            },
        ),
        migrations.AddField(
            model_name="exam",
            name="grade",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (1, "1-ci sinif"),
                    (2, "2-ci sinif"),
                    (3, "3-cü sinif"),
                    (4, "4-cü sinif"),
                    (5, "5-ci sinif"),
                    (6, "6-cı sinif"),
                    (7, "7-ci sinif"),
                    (8, "8-ci sinif"),
                    (9, "9-cu sinif"),
                    (10, "10-cu sinif"),
                    (11, "11-ci sinif"),
                ],
                help_text="Məsələn 5-ci sinif imtahanı. Boş buraxılsa qarışıq ola bilər.",
                null=True,
                verbose_name="Sinif",
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="questions",
                to="exams.subject",
                verbose_name="Fənn",
            ),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="first_name",
            field=models.CharField(blank=True, max_length=80, verbose_name="Ad"),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="last_name",
            field=models.CharField(blank=True, max_length=80, verbose_name="Soyad"),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="grade",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (1, "1-ci sinif"),
                    (2, "2-ci sinif"),
                    (3, "3-cü sinif"),
                    (4, "4-cü sinif"),
                    (5, "5-ci sinif"),
                    (6, "6-cı sinif"),
                    (7, "7-ci sinif"),
                    (8, "8-ci sinif"),
                    (9, "9-cu sinif"),
                    (10, "10-cu sinif"),
                    (11, "11-ci sinif"),
                ],
                null=True,
                verbose_name="Sinif",
            ),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="region",
            field=models.CharField(blank=True, max_length=64, verbose_name="Şəhər / bölgə"),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="baku_district",
            field=models.CharField(blank=True, max_length=64, verbose_name="Bakı rayonu"),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="address",
            field=models.CharField(blank=True, max_length=255, verbose_name="Ünvan"),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="code",
            field=models.CharField(blank=True, max_length=16, verbose_name="İş nömrəsi"),
        ),
        migrations.RunPython(seed_subjects, noop),
        migrations.RunPython(migrate_profiles, noop),
        migrations.RemoveField(
            model_name="studentprofile",
            name="district",
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="code",
            field=models.CharField(blank=True, max_length=16, null=True, unique=True, verbose_name="İş nömrəsi"),
        ),
    ]
