from django.db import migrations


def reencrypt_existing_templates(apps, schema_editor):
    """
    Re-saves every existing BiometricTemplate row so it goes through
    EncryptedBinaryField.get_prep_value() and gets encrypted.

    Reading `obj.template` already round-trips through from_db_value():
    it decrypts the value if it's already encrypted, or falls back to the
    raw legacy plaintext bytes if it isn't (see EncryptedBinaryField).
    Writing it back via update() re-encrypts via get_prep_value(), so this
    is safe to run more than once.
    """
    BiometricTemplate = apps.get_model('biometric', 'BiometricTemplate')
    for obj in BiometricTemplate.objects.all():
        BiometricTemplate.objects.filter(pk=obj.pk).update(template=obj.template)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('biometric', '0004_alter_biometrictemplate_template'),
    ]

    operations = [
        migrations.RunPython(reencrypt_existing_templates, noop_reverse),
    ]
