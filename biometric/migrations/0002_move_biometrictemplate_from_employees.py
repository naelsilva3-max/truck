import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """State-only move: BiometricTemplate becomes part of the `biometric` app.

    The physical table (`employees_biometrictemplate`) is untouched — this only
    updates which app Django's migration state considers the model to belong
    to, via `db_table`. No data is read, written, or moved.
    """

    dependencies = [
        ('biometric', '0001_initial'),
        ('employees', '0005_alter_biometrictemplate_options_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='BiometricTemplate',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('template', models.BinaryField(help_text='Dados binários do template biométrico (máx. 10 KB).', verbose_name='Template')),
                        ('finger_index', models.SmallIntegerField(default=0, help_text='Índice do dedo utilizado na captura (0 = padrão).', verbose_name='Dedo')),
                        ('enrolled_at', models.DateTimeField(auto_now_add=True, help_text='Data e hora do cadastro biométrico.', verbose_name='Cadastrado em')),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='Data e hora da última atualização do template.', verbose_name='Atualizado em')),
                        ('employee', models.OneToOneField(help_text='Funcionário associado a este template biométrico.', on_delete=django.db.models.deletion.CASCADE, related_name='biometric', to='employees.employee', verbose_name='Funcionário')),
                    ],
                    options={
                        'verbose_name': 'Template Biométrico',
                        'verbose_name_plural': 'Templates Biométricos',
                        'ordering': ['employee__name'],
                        'db_table': 'employees_biometrictemplate',
                        'indexes': [
                            models.Index(fields=['employee'], name='idx_biotemplate_employee'),
                            models.Index(fields=['finger_index'], name='idx_biotemplate_finger'),
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
