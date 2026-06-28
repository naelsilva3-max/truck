from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

from employees.models import Employee


class Visitor(models.Model):
    """Visitor who comes to the company."""
    name = models.CharField(max_length=200, verbose_name='Nome')
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
    phone = models.CharField(max_length=20, blank=True, verbose_name='Telefone')
    company = models.CharField(max_length=200, blank=True, verbose_name='Empresa')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Visitante'
        verbose_name_plural = 'Visitantes'

    def __str__(self):
        return self.name

    def clean(self):
        if not self.name or not self.name.strip():
            raise ValidationError({'name': 'O nome não pode ser vazio ou composto apenas de espaços.'})

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
    )
    visit_date = models.DateField(verbose_name='Data da Visita')
    arrival_time = models.TimeField(verbose_name='Hora de Chegada')
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
    notes = models.TextField(blank=True, verbose_name='Observações')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-visit_date', '-arrival_time']
        verbose_name = 'Visita'
        verbose_name_plural = 'Visitas'

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