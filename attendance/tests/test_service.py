"""Unit tests for AttendanceService (task 9.3)."""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from django.utils import timezone

from attendance.models import AttendanceRecord
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
        # Backdate entry so exit is at least 1s later
        open_rec = svc.get_open_record(emp.pk)
        AttendanceRecord.objects.filter(pk=open_rec.pk).update(
            entry_time=open_rec.entry_time - timedelta(seconds=2)
        )
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
