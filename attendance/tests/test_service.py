"""Unit tests for AttendanceService (task 9.3)."""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from django.utils import timezone

from attendance.exceptions import DuplicateScanError
from attendance.models import AttendanceRecord, PresenceEvent
from attendance.service import AttendanceService
from biometric.models import BiometricTemplate
from employees.models import Employee


def make_employee(**kw) -> Employee:
    defaults = dict(name="Test", role="Op", hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


@pytest.mark.django_db
class TestAttendanceService:

    def test_record_entry_creates_record(self):
        emp = make_employee()
        svc = AttendanceService()
        rec = svc.record_entry(emp.pk)
        assert rec.pk is not None
        assert rec.exit_time is None
        assert rec.employee_id == emp.pk

    def test_record_exit_sets_exit_time(self):
        emp = make_employee()
        svc = AttendanceService()
        entry = svc.record_entry(emp.pk)
        # Ensure at least 1s gap
        AttendanceRecord.objects.filter(pk=entry.pk).update(
            entry_time=entry.entry_time - timedelta(seconds=2)
        )
        rec = svc.record_exit(emp.pk)
        assert rec.exit_time is not None
        assert rec.exit_time > rec.entry_time

    def test_record_exit_no_open_record_raises(self):
        emp = make_employee()
        svc = AttendanceService()
        with pytest.raises(ValueError):
            svc.record_exit(emp.pk)

    def test_process_biometric_event_creates_entry(self):
        emp = make_employee()
        template_bytes = b"t" * 64
        BiometricTemplate.objects.create(employee=emp, template=template_bytes)

        mock_bio = MagicMock()
        mock_bio.identify.return_value = emp.pk
        svc = AttendanceService(biometric_service=mock_bio)

        rec = svc.process_biometric_event(template_bytes)
        assert rec is not None
        assert rec.exit_time is None

    def test_process_biometric_event_closes_open_record(self):
        emp = make_employee()
        template_bytes = b"t" * 64
        BiometricTemplate.objects.create(employee=emp, template=template_bytes)

        mock_bio = MagicMock()
        mock_bio.identify.return_value = emp.pk
        svc = AttendanceService(biometric_service=mock_bio)

        # First event: entry
        svc.process_biometric_event(template_bytes)
        # Backdate entry (and its PresenceEvent, past SCAN_COOLDOWN) so the
        # second call is both >=1s later and outside the duplicate-scan window.
        open_rec = svc.get_open_record(emp.pk)
        backdated = open_rec.entry_time - AttendanceService.SCAN_COOLDOWN - timedelta(seconds=1)
        AttendanceRecord.objects.filter(pk=open_rec.pk).update(entry_time=backdated)
        PresenceEvent.objects.filter(attendance_record=open_rec).update(timestamp=backdated)
        # Second event: exit
        rec = svc.process_biometric_event(template_bytes)
        assert rec.exit_time is not None

    def test_process_biometric_event_unknown_fingerprint_returns_none(self):
        mock_bio = MagicMock()
        mock_bio.identify.return_value = None
        svc = AttendanceService(biometric_service=mock_bio)
        result = svc.process_biometric_event(b"unknown")
        assert result is None

    def test_list_records_date_filter(self):
        emp = make_employee()
        svc = AttendanceService()

        now = timezone.now()
        yesterday = now - timedelta(days=1)

        # Record today
        AttendanceRecord.objects.create(
            employee=emp, entry_time=now, date=now.date()
        )
        # Record yesterday
        AttendanceRecord.objects.create(
            employee=emp, entry_time=yesterday, date=yesterday.date()
        )

        results = svc.list_records(emp.pk, start_date=now.date(), end_date=now.date())
        assert all(r.date == now.date() for r in results)
        assert results.count() == 1


@pytest.mark.django_db
class TestAttendanceServiceScanCooldown:
    def test_second_toggle_within_cooldown_raises(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)

        with pytest.raises(DuplicateScanError) as exc_info:
            svc.toggle_for_employee(emp.pk)
        assert exc_info.value.employee_name == emp.name
        assert 0 < exc_info.value.retry_after_seconds <= AttendanceService.SCAN_COOLDOWN.total_seconds()

    def test_toggle_after_cooldown_elapsed_succeeds(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)

        last_event = PresenceEvent.objects.filter(employee=emp).latest('timestamp')
        PresenceEvent.objects.filter(pk=last_event.pk).update(
            timestamp=last_event.timestamp - AttendanceService.SCAN_COOLDOWN - timedelta(seconds=1)
        )
        AttendanceRecord.objects.filter(employee=emp, exit_time__isnull=True).update(
            entry_time=last_event.timestamp - AttendanceService.SCAN_COOLDOWN - timedelta(seconds=1)
        )

        rec = svc.toggle_for_employee(emp.pk)
        assert rec.exit_time is not None

    def test_cooldown_does_not_apply_to_a_different_employee(self):
        emp1 = make_employee(name="Um")
        emp2 = make_employee(name="Dois")
        svc = AttendanceService()
        svc.toggle_for_employee(emp1.pk)

        rec = svc.toggle_for_employee(emp2.pk)  # should not raise
        assert rec.employee_id == emp2.pk


@pytest.mark.django_db
class TestAttendanceServiceStaleAutoClose:
    """
    An employee who forgets to scan out must not have their *next day's*
    arrival scan misread as the previous day's exit — the stale open record
    should be auto-closed (flagged, exit_time left for manual review) and
    the new scan should start a fresh entry instead.
    """

    def _backdate_open_record_and_event(self, emp, svc, delta):
        open_rec = svc.get_open_record(emp.pk)
        stale_time = open_rec.entry_time - delta
        AttendanceRecord.objects.filter(pk=open_rec.pk).update(entry_time=stale_time)
        PresenceEvent.objects.filter(attendance_record=open_rec).update(timestamp=stale_time)
        return open_rec

    def test_auto_close_if_stale_flags_record_past_max_open_duration(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)
        self._backdate_open_record_and_event(
            emp, svc, AttendanceService.MAX_OPEN_DURATION + timedelta(seconds=1)
        )

        closed = svc.auto_close_if_stale(emp.pk)
        assert closed is not None
        assert closed.auto_closed is True
        assert closed.exit_time is None

    def test_auto_close_if_stale_does_not_flag_record_within_max_open_duration(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)
        self._backdate_open_record_and_event(
            emp, svc, AttendanceService.MAX_OPEN_DURATION - timedelta(minutes=1)
        )

        assert svc.auto_close_if_stale(emp.pk) is None

    def test_stale_open_record_no_longer_counts_as_open(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)
        self._backdate_open_record_and_event(
            emp, svc, AttendanceService.MAX_OPEN_DURATION + timedelta(seconds=1)
        )
        svc.auto_close_if_stale(emp.pk)

        assert svc.get_open_record(emp.pk) is None

    def test_next_scan_after_stale_record_starts_new_entry_not_exit(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)  # forgotten entry, never checked out
        self._backdate_open_record_and_event(
            emp, svc, AttendanceService.MAX_OPEN_DURATION + timedelta(seconds=1)
        )

        # Next day's arrival scan
        new_record = svc.toggle_for_employee(emp.pk)

        assert new_record.exit_time is None  # a fresh entry, not the stale exit
        stale_record = AttendanceRecord.objects.exclude(pk=new_record.pk).get(employee=emp)
        assert stale_record.auto_closed is True
        assert stale_record.exit_time is None
