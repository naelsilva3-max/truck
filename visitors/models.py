from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from employee_truck_control.validators import validate_cpf
from employees.models import Employee


class Visitor(models.Model):
    """Visitor who comes to the company."""
    name = models.CharField(
        max_length=200,
        verbose_name='Nome',
        help_text='Nome completo do visitante.',
    )
    photo = models.ImageField(
        upload_to='visitors/photos/',
        null=True, blank=True,
        verbose_name='Foto do Rosto',
        help_text='Foto do rosto do visitante.',
    )
    document_photo = models.ImageField(
        upload_to='visitors/documents/',
        null=True, blank=True,
        verbose_name='Foto do Documento',
        help_text='Imagem do documento de identificação do visitante.',
    )
    phone = models.CharField(
        max_length=20, blank=True,
        verbose_name='Telefone',
        help_text='Número de telefone para contato do visitante.',
    )
    company = models.CharField(
        max_length=200, blank=True,
        verbose_name='Empresa',
        help_text='Empresa à qual o visitante pertence (se aplicável).',
    )
    rg = models.CharField(
        max_length=20, blank=True,
        verbose_name='RG',
        help_text='Número do RG do visitante (obrigatório, exceto para estrangeiros).',
    )
    cpf = models.CharField(
        max_length=14, blank=True,
        verbose_name='CPF',
        help_text='CPF do visitante, no formato 000.000.000-00 (obrigatório, exceto para estrangeiros).',
    )
    is_foreigner = models.BooleanField(
        default=False,
        verbose_name='Estrangeiro?',
        help_text='Marque se o visitante é estrangeiro e não possui RG/CPF.',
    )
    foreign_document_number = models.CharField(
        max_length=50, blank=True,
        verbose_name='Número do Documento',
        help_text='Número do documento de identificação apresentado pelo visitante estrangeiro.',
    )
    foreign_document_type = models.CharField(
        max_length=100, blank=True,
        verbose_name='Tipo de Documento',
        help_text='Tipo do documento apresentado pelo visitante estrangeiro (ex.: Passaporte, RNE).',
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
        verbose_name = 'Visitante'
        verbose_name_plural = 'Visitantes'
        indexes = [
            models.Index(fields=['name'], name='idx_visitor_name'),
            models.Index(fields=['company'], name='idx_visitor_company'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.name or not self.name.strip():
            raise ValidationError({'name': 'O nome não pode ser vazio ou composto apenas de espaços.'})

        if self.cpf:
            try:
                validate_cpf(self.cpf)
            except ValidationError as exc:
                raise ValidationError({'cpf': exc.messages})
            conflict = Visitor.objects.filter(cpf=self.cpf).exclude(pk=self.pk).exists()
            if conflict:
                raise ValidationError({'cpf': 'Já existe um visitante cadastrado com este CPF.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Visit(models.Model):
    """Record of a visitor's visit to the company."""
    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.PROTECT,
        related_name='visits',
        verbose_name='Visitante',
        help_text='Visitante que realizou a visita.',
    )
    visit_date = models.DateField(
        verbose_name='Data da Visita',
        help_text='Data em que a visita ocorreu.',
    )
    arrival_time = models.TimeField(
        verbose_name='Hora de Chegada',
        help_text='Horário de chegada do visitante.',
    )
    id_verified = models.BooleanField(
        default=False,
        verbose_name='Identificação com Foto Verificada',
        help_text='A identificação com foto do visitante foi verificada?',
    )
    responsible = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='responsible_visits',
        verbose_name='Responsável pela Visita',
        help_text='Funcionário responsável por receber o visitante.',
    )
    scheduled_departure_time = models.TimeField(
        verbose_name='Hora de Partida (Prevista)',
        help_text='Horário previsto para o término da visita / expiração do crachá.',
    )
    actual_departure_time = models.TimeField(
        null=True, blank=True,
        verbose_name='Hora Real da Partida',
        help_text='Horário em que o visitante realmente deixou o local.',
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Observações',
        help_text='Observações adicionais sobre a visita.',
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
        ordering = ['-visit_date', '-arrival_time']
        verbose_name = 'Visita'
        verbose_name_plural = 'Visitas'
        indexes = [
            models.Index(fields=['visitor', 'visit_date'], name='idx_visit_visitor_date'),
            models.Index(fields=['responsible'], name='idx_visit_responsible'),
            models.Index(fields=['visit_date'], name='idx_visit_date'),
        ]

    def __str__(self):
        return f'{self.visitor.name} — {self.visit_date} ({self.arrival_time:%H:%M})'

    @property
    def is_active(self):
        """Returns True if the visitor is still on-site (no actual departure)."""
        return self.actual_departure_time is None

    def clean(self):
        if self.scheduled_departure_time and self.arrival_time:
            if self.scheduled_departure_time <= self.arrival_time:
                raise ValidationError({
                    'scheduled_departure_time': (
                        'A hora de partida prevista deve ser posterior à hora de chegada.'
                    )
                })
        # actual_departure_time can be on a different day (e.g. visit at 23:00, departure at 00:30 next day)
        # so we only validate if the same-day comparison makes sense
        if self.actual_departure_time and self.arrival_time:
            pass  # Allow any actual departure time, as it could be on a different day

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)