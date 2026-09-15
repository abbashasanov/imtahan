from django.db import migrations


def unmark_correct_answers(apps, schema_editor):
    Choice = apps.get_model("exams", "Choice")
    Choice.objects.filter(is_correct=True).update(is_correct=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0004_exam_settings_and_question_points"),
    ]

    operations = [
        migrations.RunPython(unmark_correct_answers, noop),
    ]
