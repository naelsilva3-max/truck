from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Employee(models.Model):
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    hire_date = models.DateField()
    is_driver = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to='employees/photos/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Funcionário'
        verbose_name_plural = 'Funcionários'

    def __str__(self):
        return self.name

    def clean(self):
        # name must not be blank or whitespace-only
        if not self.name or not self.name.strip():
            raise ValidationError({'name': 'O nome não pode ser vazio ou composto apenas de espaços.'})

        # hire_date must not be in the future
        if self.hire_date and self.hire_date > timezone.now().date():
            raise ValidationError({'hire_date': 'A data de admissão não pode ser uma data futura.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class BiometricTemplate(models.Model):
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='biometric',
    )
    template = models.BinaryField()
    finger_index = models.SmallIntegerField(default=0)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Template Biométrico'
        verbose_name_plural = 'Templates Biométricos'

    def __str__(self):
        return f'Template biométrico de {self.employee.name}'

    def clean(self):
        if self.template is None:
            raise ValidationError({'template': 'O template biométrico não pode ser nulo.'})
        # BinaryField stores bytes; support both bytes and memoryview
        template_bytes = bytes(self.template)
        length = len(template_bytes)
        if length == 0:
            raise ValidationError({'template': 'O template biométrico não pode ser vazio (0 bytes).'})
        if length > 10_240:
            raise ValidationError(
                {'template': f'O template biométrico excede o tamanho máximo permitido de 10 KB (tamanho atual: {length} bytes).'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
