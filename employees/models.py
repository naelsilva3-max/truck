from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from employee_truck_control.validators import validate_cep, validate_cpf


class Employee(models.Model):
    name = models.CharField(
        max_length=200,
        verbose_name='Nome',
        help_text='Nome completo do funcionário.',
    )
    role = models.CharField(
        max_length=100,
        verbose_name='Cargo',
        help_text='Cargo ou função do funcionário na empresa.',
    )
    department = models.CharField(
        max_length=100, blank=True,
        verbose_name='Departamento',
        help_text='Departamento ao qual o funcionário está alocado.',
    )
    phone = models.CharField(
        max_length=20, blank=True,
        verbose_name='Telefone',
        help_text='Número de telefone para contato.',
    )
    rg = models.CharField(
        max_length=20, blank=True,
        verbose_name='RG',
        help_text='Número do RG do funcionário (opcional).',
    )
    cpf = models.CharField(
        max_length=14, blank=True,
        verbose_name='CPF',
        help_text='CPF do funcionário, no formato 000.000.000-00 (opcional).',
    )
    is_foreigner = models.BooleanField(
        default=False,
        verbose_name='Estrangeiro?',
        help_text='Marque se o funcionário é estrangeiro e não possui RG/CPF.',
    )
    foreign_document_number = models.CharField(
        max_length=50, blank=True,
        verbose_name='Número do Documento',
        help_text='Número do documento de identificação apresentado pelo funcionário estrangeiro.',
    )
    foreign_document_type = models.CharField(
        max_length=100, blank=True,
        verbose_name='Tipo de Documento',
        help_text='Tipo do documento apresentado pelo funcionário estrangeiro (ex.: Passaporte, RNE).',
    )
    address = models.CharField(
        max_length=255, blank=True,
        verbose_name='Endereço',
        help_text='Endereço completo do funcionário (opcional).',
    )
    cep = models.CharField(
        max_length=9, blank=True,
        verbose_name='CEP',
        help_text='CEP do endereço, no formato 00000-000 (opcional).',
    )
    hire_date = models.DateField(
        verbose_name='Data de Admissão',
        help_text='Data em que o funcionário foi contratado.',
    )
    is_driver = models.BooleanField(
        default=False,
        verbose_name='É Motorista?',
        help_text='Indica se o funcionário está habilitado como motorista.',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Ativo?',
        help_text='Indica se o funcionário está ativo na empresa.',
    )
    photo = models.ImageField(
        upload_to='employees/photos/', null=True, blank=True,
        verbose_name='Foto',
        help_text='Foto de identificação do funcionário.',
    )
    document_photo = models.ImageField(
        upload_to='employees/documents/',
        null=True, blank=True,
        verbose_name='Foto do Documento',
        help_text='Imagem do documento de identificação do funcionário (RG, CNH, etc.).',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em',
        help_text='Data e hora de criação do registro.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em',
        help_text='Data e hora da última atualização do registro.',
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Funcionário'
        verbose_name_plural = 'Funcionários'
        indexes = [
            models.Index(fields=['name'], name='idx_employee_name'),
            models.Index(fields=['is_active'], name='idx_employee_active'),
            models.Index(fields=['department'], name='idx_employee_department'),
            models.Index(fields=['is_driver'], name='idx_employee_driver'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        # name must not be blank or whitespace-only
        if not self.name or not self.name.strip():
            raise ValidationError({'name': 'O nome não pode ser vazio ou composto apenas de espaços.'})

        # hire_date must not be in the future
        if self.hire_date and self.hire_date > timezone.now().date():
            raise ValidationError({'hire_date': 'A data de admissão não pode ser uma data futura.'})

        if self.cpf:
            try:
                validate_cpf(self.cpf)
            except ValidationError as exc:
                raise ValidationError({'cpf': exc.messages})
            conflict = Employee.objects.filter(cpf=self.cpf).exclude(pk=self.pk).exists()
            if conflict:
                raise ValidationError({'cpf': 'Já existe um funcionário cadastrado com este CPF.'})

        if self.cep:
            try:
                validate_cep(self.cep)
            except ValidationError as exc:
                raise ValidationError({'cep': exc.messages})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
