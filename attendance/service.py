from __future__ import annotations

import logging
from datetime import date as _date, timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from attendance.exceptions import DuplicateScanError
from attendance.models import AttendanceRecord, PresenceEvent
from biometric.models import BiometricTemplate

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from biometric.service import BiometricService as _BiometricServiceType

logger = logging.getLogger(__name__)


def presence_label(direction: str, is_lunch: bool) -> str:
    """Human label for a (direction, is_lunch) pair, shared by the kiosk API response and callers outside Django templates (which branch on direction/is_lunch directly)."""
    if is_lunch:
        return 'Retorno do Almoço' if direction == PresenceEvent.IN else 'Saída para o Almoço'
    return 'Entrada' if direction == PresenceEvent.IN else 'Saída'


def next_action_label(direction: str, is_lunch: bool) -> str:
    """Label for the scan toggle_for_employee would perform *next*, given the employee's current (direction, is_lunch) status — mirrors the state order in toggle_for_employee."""
    if direction == PresenceEvent.OUT and not is_lunch:
        return 'Entrada'
    if direction == PresenceEvent.IN and not is_lunch:
        return 'Saída para o Almoço'
    if direction == PresenceEvent.OUT and is_lunch:
        return 'Retorno do Almoço'
    return 'Saída'


class AttendanceService:

    # Minimum time between two registrations (IN or OUT, in either order)
    # for the same employee — guards against accidental double-taps at the
    # reader (or a stale/duplicate identification) being recorded as two
    # separate attendance events.
    SCAN_COOLDOWN = timedelta(minutes=3)

    # Longest an AttendanceRecord is allowed to stay open before it's treated
    # as abandoned (employee forgot to scan out) rather than a real ongoing
    # shift. Covers the longest legitimate shift plus overtime with margin;
    # once exceeded the record is auto-closed (flagged, not given a guessed
    # exit_time) so the next scan starts a fresh entry instead of being
    # misread as that stale record's exit.
    MAX_OPEN_DURATION = timedelta(hours=16)

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
            .filter(employee_id=employee_id, exit_time__isnull=True, auto_closed=False)
            .first()
        )

    def auto_close_if_stale(self, employee_id: int) -> AttendanceRecord | None:
        """
        If this employee's open record has been open longer than
        MAX_OPEN_DURATION, flag it as auto_closed instead of leaving it to
        be matched as an "exit" by whatever scan comes next (which could be
        a day later, and would record that day's arrival as the previous
        day's departure). Does not guess exit_time — the record stays
        exit_time=None for an admin to fill in on the review screen.
        """
        record = (
            AttendanceRecord.objects
            .filter(employee_id=employee_id, exit_time__isnull=True, auto_closed=False)
            .first()
        )
        if record is None:
            return None
        if timezone.now() - record.entry_time <= self.MAX_OPEN_DURATION:
            return None
        record.auto_closed = True
        record.save()
        logger.warning(
            "Attendance record %s for employee %s auto-closed as stale (open since %s).",
            record.pk, employee_id, record.entry_time,
        )
        return record

    def get_current_status(self, employee_id: int) -> tuple[str, bool, object | None]:
        """Return (direction, is_lunch, timestamp) of the last PresenceEvent, or ('OUT', False, None)."""
        last = (
            PresenceEvent.objects
            .filter(employee_id=employee_id)
            .order_by('-timestamp')
            .first()
        )
        if last is None:
            return PresenceEvent.OUT, False, None
        return last.direction, last.is_lunch, last.timestamp

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

    def record_lunch_start(self, employee_id: int) -> AttendanceRecord:
        self._check_active(employee_id)
        record = self.get_open_record(employee_id)
        if record is None or record.lunch_start is not None:
            raise ValueError(f"No attendance record awaiting lunch start for employee {employee_id}.")
        now = timezone.now()
        record.lunch_start = now
        record.save()
        PresenceEvent.objects.create(
            employee_id=employee_id,
            direction=PresenceEvent.OUT,
            is_lunch=True,
            timestamp=now,
            attendance_record=record,
        )
        logger.info("Lunch start recorded for employee %s at %s.", employee_id, now)
        return record

    def record_lunch_end(self, employee_id: int) -> AttendanceRecord:
        self._check_active(employee_id)
        record = self.get_open_record(employee_id)
        if record is None or record.lunch_start is None or record.lunch_end is not None:
            raise ValueError(f"No attendance record awaiting lunch end for employee {employee_id}.")
        now = timezone.now()
        record.lunch_end = now
        record.save()
        PresenceEvent.objects.create(
            employee_id=employee_id,
            direction=PresenceEvent.IN,
            is_lunch=True,
            timestamp=now,
            attendance_record=record,
        )
        logger.info("Lunch end recorded for employee %s at %s.", employee_id, now)
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

    def _check_cooldown(self, employee_id: int) -> None:
        _, _, last_ts = self.get_current_status(employee_id)
        if last_ts is None:
            return
        elapsed = timezone.now() - last_ts
        if elapsed < self.SCAN_COOLDOWN:
            from employees.models import Employee
            employee = Employee.objects.get(pk=employee_id)
            retry_after = max(1, int((self.SCAN_COOLDOWN - elapsed).total_seconds()))
            raise DuplicateScanError(employee.name, retry_after)

    def toggle_for_employee(self, employee_id: int) -> AttendanceRecord:
        """
        Advance an already-identified employee through the fixed 4-scan daily
        cycle — entrada, saída para o almoço, retorno do almoço, saída — one
        step per call, based on which timestamps the day's open record still
        lacks:
          1. no open record            -> record_entry
          2. lunch_start not set       -> record_lunch_start
          3. lunch_start set, no lunch_end -> record_lunch_end
          4. lunch cycle done          -> record_exit (closes the record)
        The cycle is fixed/ordinal, not time-of-day-based: every employee is
        expected to scan all 4 times, regardless of when in the day each
        scan happens. A record left open past MAX_OPEN_DURATION (see
        auto_close_if_stale) is flagged and ignored here, so this scan starts
        a new entry instead of being read as a step in that stale record.

        Propagates Employee.DoesNotExist and ValueError (inactive employee)
        raised by the record_* methods' _check_active, and DuplicateScanError
        (see SCAN_COOLDOWN/_check_cooldown) — callers (e.g. the kiosk scan
        API view) map these to 4xx responses.
        """
        self._check_active(employee_id)
        self._check_cooldown(employee_id)
        self.auto_close_if_stale(employee_id)
        open_record = self.get_open_record(employee_id)
        if open_record is None:
            return self.record_entry(employee_id)
        if open_record.lunch_start is None:
            return self.record_lunch_start(employee_id)
        if open_record.lunch_end is None:
            return self.record_lunch_end(employee_id)
        return self.record_exit(employee_id)

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

        return self.toggle_for_employee(employee_id)

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
