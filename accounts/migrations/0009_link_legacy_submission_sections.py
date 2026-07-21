from django.db import migrations


def link_legacy_submission_sections(apps, schema_editor):
    DynamicFormSubmission = apps.get_model('accounts', 'DynamicFormSubmission')
    Section = apps.get_model('accounts', 'Section')

    sections_by_code = {
        section.code: section
        for section in Section.objects.all()
    }

    for submission in DynamicFormSubmission.objects.filter(
        assigned_section__isnull=True,
    ).exclude(section__isnull=True).exclude(section=''):
        legacy = (submission.section or '').strip()
        if not legacy:
            continue
        # Prefer exact code match; otherwise first comma-separated token
        code = legacy.split(',')[0].strip()[:20]
        section = sections_by_code.get(code)
        if section:
            submission.assigned_section = section
            submission.section = section.code
            submission.save(update_fields=['assigned_section', 'section'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_form_submission_per_section'),
    ]

    operations = [
        migrations.RunPython(link_legacy_submission_sections, noop_reverse),
    ]
