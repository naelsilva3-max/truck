from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('accounts', 'UserProfile')
    for user in User.objects.all():
        UserProfile.objects.get_or_create(user=user, defaults={'role': 'master' if user.is_superuser else 'simple'})


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, migrations.RunPython.noop),
    ]
