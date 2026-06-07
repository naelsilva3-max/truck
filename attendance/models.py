from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models

from employees.models import Employee


class AttendanceRecord(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='attendance_records',
    )
    entry_time = models.DateTimeField()
    exit_time = models.DateTimeField(null=True, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-entry_time']
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['employee', 'exit_time']),
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
        if self.exit_time is not None and self.entry_time is not None:
            if self.exit_time < self.entry_time + timedelta(seconds=1):
                raise ValidationError({
                    'exit_time': (
                        'O horário de saída deve ser pelo menos 1 segundo '
                        'posterior ao horário de entrada.'
                    )
                })

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
    )
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    timestamp = models.DateTimeField()
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.PROTECT,
        related_name='presence_events',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['employee', 'timestamp'])]
        verbose_name = 'Evento de Presença'
        verbose_name_plural = 'Eventos de Presença'

    def __str__(self):
        return f'{self.employee.name} — {self.direction} — {self.timestamp:%d/%m/%Y %H:%M:%S}'

    def delete(self, *args, **kwargs):
        raise PermissionError('Physical deletion of PresenceEvent is not allowed.')
