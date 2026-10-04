from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0007_alter_profile_location_choices"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "certificate_contact_phone",
                    models.CharField(
                        blank=True,
                        help_text="Nəticə vərəqəsində «Sertifikat əldə etmək üçün bizə yazın» yanında görünür.",
                        max_length=32,
                        verbose_name="Sertifikat əlaqə nömrəsi",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sayt tənzimləməsi",
                "verbose_name_plural": "Sayt tənzimləməsi",
            },
        ),
    ]
