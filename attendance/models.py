from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models

from employees.models import Employee


class AttendanceRecord(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='attendance_records',
        verbose_name='Funcionário',
        help_text='Funcionário ao qual este registro de ponto pertence.',
    )
    entry_time = models.DateTimeField(
        verbose_name='Entrada',
        help_text='Data e hora da entrada do funcionário.',
    )
    lunch_start = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Saída para Almoço',
        help_text='Data e hora em que o funcionário saiu para o almoço.',
    )
    lunch_end = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Retorno do Almoço',
        help_text='Data e hora em que o funcionário retornou do almoço.',
    )
    exit_time = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Saída',
        help_text='Data e hora da saída do funcionário (nulo = ainda em aberto).',
    )
    date = models.DateField(
        verbose_name='Data',
        help_text='Data do registro (preenchida automaticamente pela entrada).',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em',
        help_text='Data e hora de criação do registro.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em',
        help_text='Data e hora da última atualização (ex.: quando a saída é registrada num registro em aberto).',
    )
    auto_closed = models.BooleanField(
        default=False,
        verbose_name='Fechado automaticamente',
        help_text=(
            'Marcado quando o funcionário esqueceu de bater a saída e o '
            'registro ficou aberto além do turno máximo permitido — deixa '
            'de contar como "em aberto" para a próxima batida (que passa a '
            'gerar uma nova entrada) e aparece na tela de revisão até que '
            'um administrador preencha a saída real.'
        ),
    )

    class Meta:
        ordering = ['-entry_time']
        indexes = [
            models.Index(fields=['employee', 'date'], name='idx_attendance_emp_date'),
            models.Index(fields=['employee', 'exit_time'], name='idx_attendance_emp_exit'),
            models.Index(fields=['date'], name='idx_attendance_date'),
        ]
        verbose_name = 'Registro de Ponto'
        verbose_name_plural = 'Registros de Ponto'

    def __str__(self):
        return (
            f'{self.employee.name} — {self.date} '
            f'{self.entry_time:%H:%M} → '
            f'{self.exit_time:%H:%M}' if self.exit_time else
            f'{self.employee.name} — {self.date} {self.entry_time:%H:%M} → em aberto'
        )

    def clean(self):
        """
        Validates chronological order across whichever of the four
        punch-clock timestamps are set — entrada, saída para o almoço,
        retorno do almoço, saída — skipping any that are absent (e.g. a
        manually-corrected record may only have entry_time and exit_time,
        with no lunch pair).
        """
        prior_field, prior_value = None, None
        for field_name in ('entry_time', 'lunch_start', 'lunch_end', 'exit_time'):
            value = getattr(self, field_name)
            if value is None:
                continue
            if prior_value is not None and value < prior_value + timedelta(seconds=1):
                raise ValidationError({
                    field_name: (
                        f'O horário de "{self._meta.get_field(field_name).verbose_name}" deve ser '
                        f'pelo menos 1 segundo posterior ao horário de '
                        f'"{self._meta.get_field(prior_field).verbose_name}".'
                    )
                })
            prior_field, prior_value = field_name, value

    def save(self, *args, **kwargs):
        if self.entry_time is not None:
            self.date = self.entry_time.date()
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError(
            'Physical deletion of AttendanceRecord is not allowed; '
            'use soft-delete instead.'
        )


class PresenceEvent(models.Model):
    """Immutable log of every biometric scan — one row per scan, never deleted."""

    IN = 'IN'
    OUT = 'OUT'
    DIRECTION_CHOICES = [(IN, 'Entrada'), (OUT, 'Saída')]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='presence_events',
        verbose_name='Funcionário',
        help_text='Funcionário que gerou o evento biométrico.',
    )
    direction = models.CharField(
        max_length=3, choices=DIRECTION_CHOICES,
        verbose_name='Direção',
        help_text='Direção do evento: Entrada (IN) ou Saída (OUT).',
    )
    is_lunch = models.BooleanField(
        default=False,
        verbose_name='É do Almoço?',
        help_text=(
            'Marca este evento como parte do intervalo de almoço — '
            'combinado com "direction", distingue Saída p/ Almoço (OUT) '
            'de Retorno do Almoço (IN), em vez da Entrada/Saída do dia.'
        ),
    )
    timestamp = models.DateTimeField(
        verbose_name='Data/Hora',
        help_text='Data e hora exata do evento biométrico.',
    )
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.PROTECT,
        related_name='presence_events',
        null=True, blank=True,
        verbose_name='Registro de Ponto',
        help_text='Registro de ponto associado a este evento (se houver).',
    )

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['employee', 'timestamp'], name='idx_presence_emp_ts'),
            models.Index(fields=['direction'], name='idx_presence_direction'),
        ]
        verbose_name = 'Evento de Presença'
        verbose_name_plural = 'Eventos de Presença'

    def __str__(self):
        return f'{self.employee.name} — {self.direction} — {self.timestamp:%d/%m/%Y %H:%M:%S}'

    def delete(self, *args, **kwargs):
        raise PermissionError('Physical deletion of PresenceEvent is not allowed.')
