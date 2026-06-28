from __future__ import annotations

import logging
from datetime import date as _date
from typing import TYPE_CHECKING

from django.utils import timezone

from attendance.models import AttendanceRecord, PresenceEvent
from employees.models import BiometricTemplate

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from biometric.service import BiometricService as _BiometricServiceType

logger = logging.getLogger(__name__)


class AttendanceService:

    def __init__(self, biometric_service: '_BiometricServiceType | None' = None) -> None:
        self._biometric_service = biometric_service

    def _get_biometric_service(self) -> '_BiometricServiceType':
        if self._biometric_service is None:
            from biometric.service import BiometricService
            self._biometric_service = BiometricService()
        return self._biometric_service

    def get_open_record(self, employee_id: int) -> AttendanceRecord | None:
        return (
            AttendanceRecord.objects
            .filter(employee_id=employee_id, exit_time__isnull=True)
            .first()
        )

    def get_current_status(self, employee_id: int) -> tuple[str, object | None]:
        """Return (direction, timestamp) of the last PresenceEvent, or ('OUT', None)."""
        last = (
            PresenceEvent.objects
            .filter(employee_id=employee_id)
            .order_by('-timestamp')
            .first()
        )
        if last is None:
            return PresenceEvent.OUT, None
        return last.direction, last.timestamp

    def _check_active(self, employee_id: int) -> None:
        from employees.models import Employee
        emp = Employee.objects.get(pk=employee_id)
        if not emp.is_active:
            raise ValueError(f'Funcionário {emp.name} está inativo e não pode ter entrada/saída registrada.')

    def record_entry(self, employee_id: int) -> AttendanceRecord:
        self._check_active(employee_id)
        now = timezone.now()
        record = AttendanceRecord(employee_id=employee_id, entry_time=now, date=now.date())
        record.save()
        PresenceEvent.objects.create(
            employee_id=employee_id,
            direction=PresenceEvent.IN,
            timestamp=now,
            attendance_record=record,
        )
        logger.info("Entry recorded for employee %s at %s.", employee_id, now)
        return record

    def record_exit(self, employee_id: int) -> AttendanceRecord:
        self._check_active(employee_id)
        record = self.get_open_record(employee_id)
        if record is None:
            raise ValueError(f"No open attendance record found for employee {employee_id}.")
        now = timezone.now()
        record.exit_time = now
        record.save()
        PresenceEvent.objects.create(
            employee_id=employee_id,
            direction=PresenceEvent.OUT,
            timestamp=now,
            attendance_record=record,
        )
        logger.info("Exit recorded for employee %s at %s.", employee_id, now)
        return record

    def process_biometric_event(self, template: bytes) -> AttendanceRecord | None:
        bio_service = self._get_biometric_service()

        enrolled: list[tuple[int, bytes]] = [
            (bt.employee_id, bytes(bt.template))
            for bt in BiometricTemplate.objects.select_related('employee').all()
        ]

        employee_id: int | None = bio_service.identify(template, enrolled)

        if employee_id is None:
            logger.warning('digital desconhecida')
            return None

        open_record = self.get_open_record(employee_id)
        if open_record is None:
            return self.record_entry(employee_id)
        else:
            return self.record_exit(employee_id)

    def list_records(
        self,
        employee_id: int,
        start_date: '_date | None' = None,
        end_date: '_date | None' = None,
    ) -> 'QuerySet[AttendanceRecord]':
        qs = (
            AttendanceRecord.objects
            .filter(employee_id=employee_id)
            .order_by('-entry_time')
        )
        if start_date is not None:
            qs = qs.filter(date__gte=start_date)
        if end_date is not None:
            qs = qs.filter(date__lte=end_date)
        return qs
