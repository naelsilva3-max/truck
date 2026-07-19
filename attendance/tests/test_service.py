"""Unit tests for AttendanceService (task 9.3)."""
import pytest
from datetime import date, time as dt_time, timedelta
from unittest.mock import MagicMock, patch

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


@pytest.fixture
def in_lunch_window(monkeypatch):
    """Force AttendanceService._within_lunch_window() to True, so the 2nd
    scan-of-the-day tests are deterministic regardless of wall-clock time
    when the suite actually runs (see toggle_for_employee's real-time check)."""
    monkeypatch.setattr(AttendanceService, '_within_lunch_window', staticmethod(lambda: True))


@pytest.fixture
def outside_lunch_window(monkeypatch):
    """Force AttendanceService._within_lunch_window() to False — the 2nd scan of the day should close the day immediately instead of starting a lunch leg."""
    monkeypatch.setattr(AttendanceService, '_within_lunch_window', staticmethod(lambda: False))


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

    def test_process_biometric_event_advances_to_lunch_start(self, in_lunch_window):
        """The 2nd scan of the day is now "saída para o almoço", not "saída" — see TestAttendanceServiceLunchCycle for the full 4-scan cycle."""
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
        # Second event: saída para o almoço
        rec = svc.process_biometric_event(template_bytes)
        assert rec.lunch_start is not None
        assert rec.exit_time is None

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

    def test_toggle_after_cooldown_elapsed_succeeds(self, in_lunch_window):
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

        # 2nd scan of the day advances to "saída para o almoço", not a full exit.
        rec = svc.toggle_for_employee(emp.pk)
        assert rec.lunch_start is not None
        assert rec.exit_time is None

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


def _advance_past_cooldown(emp, svc):
    """Backdate the employee's most recent touch — the PresenceEvent and
    every AttendanceRecord timestamp set so far, shifted together by the
    same delta so their relative order is preserved — past SCAN_COOLDOWN,
    so the next toggle_for_employee call isn't rejected as a duplicate scan
    and satisfies the model's 1-second ordering (tests otherwise run several
    calls within the same fraction of a second)."""
    shift = AttendanceService.SCAN_COOLDOWN + timedelta(seconds=1)
    last_event = PresenceEvent.objects.filter(employee=emp).latest('timestamp')
    PresenceEvent.objects.filter(pk=last_event.pk).update(timestamp=last_event.timestamp - shift)
    record = svc.get_open_record(emp.pk)
    if record is None:
        return
    updates = {
        field: getattr(record, field) - shift
        for field in ('entry_time', 'lunch_start', 'lunch_end', 'exit_time')
        if getattr(record, field) is not None
    }
    AttendanceRecord.objects.filter(pk=record.pk).update(**updates)


@pytest.mark.django_db
class TestAttendanceServiceLunchCycle:
    """
    Every employee is expected to scan up to 4 times a day, in order —
    entrada, saída para o almoço, retorno do almoço, saída — via
    toggle_for_employee. These tests cover the full cycle happening inside
    the lunch window (in_lunch_window fixture); see
    TestAttendanceServiceLunchWindow for the 2nd-scan time-of-day
    disambiguation itself (skip-lunch case included).
    """

    def test_full_daily_cycle_in_order(self, in_lunch_window):
        emp = make_employee()
        svc = AttendanceService()

        entry = svc.toggle_for_employee(emp.pk)
        assert entry.entry_time is not None
        assert entry.lunch_start is None and entry.exit_time is None
        _advance_past_cooldown(emp, svc)

        lunch_out = svc.toggle_for_employee(emp.pk)
        assert lunch_out.pk == entry.pk
        assert lunch_out.lunch_start is not None
        assert lunch_out.lunch_end is None and lunch_out.exit_time is None
        _advance_past_cooldown(emp, svc)

        lunch_in = svc.toggle_for_employee(emp.pk)
        assert lunch_in.pk == entry.pk
        assert lunch_in.lunch_end is not None
        assert lunch_in.exit_time is None
        _advance_past_cooldown(emp, svc)

        exit_ = svc.toggle_for_employee(emp.pk)
        assert exit_.pk == entry.pk
        assert exit_.exit_time is not None

        # A 5th scan starts a brand-new record, not another step on this one.
        _advance_past_cooldown(emp, svc)
        next_day_entry = svc.toggle_for_employee(emp.pk)
        assert next_day_entry.pk != entry.pk
        assert next_day_entry.exit_time is None

    def test_presence_events_marked_is_lunch_for_lunch_steps_only(self, in_lunch_window):
        emp = make_employee()
        svc = AttendanceService()

        svc.toggle_for_employee(emp.pk)  # entrada
        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # saída almoço
        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # retorno almoço
        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # saída

        events = list(PresenceEvent.objects.filter(employee=emp).order_by('timestamp'))
        assert [e.is_lunch for e in events] == [False, True, True, False]
        assert [e.direction for e in events] == [
            PresenceEvent.IN, PresenceEvent.OUT, PresenceEvent.IN, PresenceEvent.OUT,
        ]

    def test_record_lunch_start_requires_open_record(self):
        emp = make_employee()
        svc = AttendanceService()
        with pytest.raises(ValueError):
            svc.record_lunch_start(emp.pk)

    def test_record_lunch_start_twice_raises(self):
        emp = make_employee()
        svc = AttendanceService()
        entry = svc.record_entry(emp.pk)
        AttendanceRecord.objects.filter(pk=entry.pk).update(entry_time=entry.entry_time - timedelta(seconds=2))
        svc.record_lunch_start(emp.pk)
        with pytest.raises(ValueError):
            svc.record_lunch_start(emp.pk)

    def test_record_lunch_end_requires_lunch_start_first(self):
        emp = make_employee()
        svc = AttendanceService()
        svc.record_entry(emp.pk)
        with pytest.raises(ValueError):
            svc.record_lunch_end(emp.pk)

    def test_record_lunch_end_twice_raises(self):
        emp = make_employee()
        svc = AttendanceService()
        entry = svc.record_entry(emp.pk)
        AttendanceRecord.objects.filter(pk=entry.pk).update(entry_time=entry.entry_time - timedelta(seconds=4))
        lunch_start = svc.record_lunch_start(emp.pk)
        AttendanceRecord.objects.filter(pk=lunch_start.pk).update(lunch_start=lunch_start.lunch_start - timedelta(seconds=2))
        svc.record_lunch_end(emp.pk)
        with pytest.raises(ValueError):
            svc.record_lunch_end(emp.pk)

    def test_get_current_status_reflects_lunch_stage(self, in_lunch_window):
        emp = make_employee()
        svc = AttendanceService()

        svc.toggle_for_employee(emp.pk)  # entrada
        direction, is_lunch, _ = svc.get_current_status(emp.pk)
        assert (direction, is_lunch) == (PresenceEvent.IN, False)

        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # saída almoço
        direction, is_lunch, _ = svc.get_current_status(emp.pk)
        assert (direction, is_lunch) == (PresenceEvent.OUT, True)

        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # retorno almoço
        direction, is_lunch, _ = svc.get_current_status(emp.pk)
        assert (direction, is_lunch) == (PresenceEvent.IN, True)

        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # saída
        direction, is_lunch, _ = svc.get_current_status(emp.pk)
        assert (direction, is_lunch) == (PresenceEvent.OUT, False)


@pytest.mark.django_db
class TestAttendanceRecordLunchOrderingValidation:
    def test_lunch_start_before_entry_rejected(self):
        emp = make_employee()
        now = timezone.now()
        record = AttendanceRecord(employee=emp, entry_time=now, lunch_start=now - timedelta(hours=1))
        with pytest.raises(Exception):
            record.save()

    def test_lunch_end_before_lunch_start_rejected(self):
        emp = make_employee()
        now = timezone.now()
        record = AttendanceRecord(
            employee=emp, entry_time=now,
            lunch_start=now + timedelta(hours=4),
            lunch_end=now + timedelta(hours=3),
        )
        with pytest.raises(Exception):
            record.save()

    def test_exit_before_lunch_end_rejected(self):
        emp = make_employee()
        now = timezone.now()
        record = AttendanceRecord(
            employee=emp, entry_time=now,
            lunch_start=now + timedelta(hours=4),
            lunch_end=now + timedelta(hours=5, minutes=30),
            exit_time=now + timedelta(hours=5),
        )
        with pytest.raises(Exception):
            record.save()

    def test_manual_correction_skipping_lunch_pair_is_allowed(self):
        """A record fixed via the review screen may only ever get entry_time + exit_time set, with no lunch pair — must remain valid."""
        emp = make_employee()
        now = timezone.now()
        record = AttendanceRecord(employee=emp, entry_time=now, exit_time=now + timedelta(hours=8))
        record.save()
        assert record.pk is not None


@pytest.mark.django_db
class TestAttendanceServiceLunchWindow:
    """
    The 2nd scan of the day is the one ambiguous case: is the employee
    leaving for lunch or leaving for the day? Disambiguated by whether
    "now" falls inside AttendanceService.LUNCH_WINDOW_START/END — everyone
    else (1st, 3rd, 4th scans) is unaffected by time of day.
    """

    def test_second_scan_inside_window_starts_lunch(self, in_lunch_window):
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)  # entrada
        _advance_past_cooldown(emp, svc)

        record = svc.toggle_for_employee(emp.pk)

        assert record.lunch_start is not None
        assert record.exit_time is None

    def test_second_scan_outside_window_closes_the_day(self, outside_lunch_window):
        """An employee who skips lunch (or forgets the lunch-out scan) and
        touches again outside the lunch window must have their day closed
        immediately — not left open waiting for a "retorno do almoço" that
        was never coming, which used to only get caught by the ~16h
        MAX_OPEN_DURATION auto-close and showed a wrong "em almoço" status
        in the meantime."""
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)  # entrada
        _advance_past_cooldown(emp, svc)

        record = svc.toggle_for_employee(emp.pk)

        assert record.lunch_start is None
        assert record.exit_time is not None

    def test_third_scan_is_lunch_end_regardless_of_window(self, in_lunch_window):
        """Once lunch has genuinely started, the return scan is read as such any time — the window only disambiguates the 2nd scan."""
        emp = make_employee()
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)  # entrada
        _advance_past_cooldown(emp, svc)
        svc.toggle_for_employee(emp.pk)  # saída almoço (inside window)
        _advance_past_cooldown(emp, svc)

        with patch.object(AttendanceService, '_within_lunch_window', staticmethod(lambda: False)):
            record = svc.toggle_for_employee(emp.pk)  # retorno, well outside any lunch window

        assert record.lunch_end is not None
        assert record.exit_time is None

    def test_within_lunch_window_boundaries(self):
        with patch('attendance.service.timezone.localtime') as mock_localtime:
            mock_localtime.return_value.time.return_value = dt_time(12, 0)
            assert AttendanceService._within_lunch_window() is True

            mock_localtime.return_value.time.return_value = dt_time(10, 59)
            assert AttendanceService._within_lunch_window() is False

            mock_localtime.return_value.time.return_value = dt_time(14, 30)
            assert AttendanceService._within_lunch_window() is True

            mock_localtime.return_value.time.return_value = dt_time(14, 31)
            assert AttendanceService._within_lunch_window() is False
