from django.db import migrations


class Migration(migrations.Migration):
    """State-only move: BiometricTemplate now lives in biometric/migrations
    (see biometric.0002_move_biometrictemplate_from_employees). The physical
    table is untouched — `database_operations` is empty on purpose.
    """

    dependencies = [
        ('employees', '0005_alter_biometrictemplate_options_and_more'),
        ('biometric', '0002_move_biometrictemplate_from_employees'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='BiometricTemplate'),
            ],
            database_operations=[],
        ),
    ]
