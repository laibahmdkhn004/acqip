from django.db import migrations


ROLE_LABELS = {
    'admin': 'Admin',
    'faculty': 'Faculty',
    'crc_member': 'CRC Member',
    'lab_instructor': 'Lab Instructor',
}


def seed_roles_and_backfill(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    User = apps.get_model('accounts', 'User')

    role_by_code = {}
    for code, name in ROLE_LABELS.items():
        role_obj, _ = Role.objects.get_or_create(code=code, defaults={'name': name})
        role_by_code[code] = role_obj

    for user in User.objects.all():
        primary = user.role or 'faculty'
        if primary not in role_by_code:
            primary = 'faculty'
            user.role = primary
            user.save(update_fields=['role'])
        user.roles.set([role_by_code[primary]])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_user_multiple_roles'),
    ]

    operations = [
        migrations.RunPython(seed_roles_and_backfill, noop_reverse),
    ]
