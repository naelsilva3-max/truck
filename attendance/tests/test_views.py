from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from attendance.models import AttendanceRecord, PresenceEvent
from attendance.service import AttendanceService
from employees.models import Employee


def make_user():
    return User.objects.create_user(username='plain', password='pass')


def make_admin_user():
    # AttendancePendingReviewView requires role admin/master (EditRequiredMixin);
    # is_superuser maps to role 'master' (accounts.mixins.get_role).
    return User.objects.create_user(username='boss', password='pass', is_superuser=True)


def make_employee(**kw):
    defaults = dict(name='Test Employee', role='Op', hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_event(employee, timestamp, direction=PresenceEvent.IN):
    return PresenceEvent.objects.create(employee=employee, direction=direction, timestamp=timestamp)


@pytest.mark.django_db
class TestPresenceHistoryLivePoll:
    def test_since_returns_only_newer_events(self):
        user = make_user()
        emp = make_employee()
        now = timezone.now()
        older = make_event(emp, now - timedelta(minutes=10))
        newer = make_event(emp, now, direction=PresenceEvent.OUT)

        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('presence_history'),
            {'type': 'employees', 'since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert emp.name in body['html']
        assert body['newest'] == newer.timestamp.isoformat()

    def test_since_with_no_new_events_returns_empty(self):
        user = make_user()
        emp = make_employee()
        now = timezone.now()
        make_event(emp, now - timedelta(minutes=10))

        client = Client()
        client.force_login(user)

        since = now.isoformat()
        response = client.get(
            reverse('presence_history'),
            {'type': 'employees', 'since': since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 0
        assert body['newest'] == since

    def test_since_ignored_without_ajax_header(self):
        """Without the XHR header, `since` is ignored and the normal HTML page renders."""
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('presence_history'), {'since': timezone.now().isoformat()})

        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/html')

    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('presence_history'), {'since': timezone.now().isoformat()})
        assert response.status_code == 302


@pytest.mark.django_db
class TestPresenceHistoryEmptyState:
    def test_renders_with_zero_events(self):
        """Regression: the live-poll table must render (even empty) so
        polling can attach without requiring a reload once the first event
        exists."""
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('presence_history'))

        assert response.status_code == 200
        assert b'infinite-tbody' in response.content
        assert b'startLivePoll' in response.content
        assert 'Nenhum registro encontrado'.encode() in response.content


@pytest.mark.django_db
class TestEmployeeListPresenceWidgetEmptyState:
    def test_renders_with_zero_events(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('employees:list'))

        assert response.status_code == 200
        assert b'history-tbody' in response.content
        assert b'startLivePoll' in response.content


@pytest.mark.django_db
class TestAttendanceListLivePolling:
    def test_new_check_in_is_picked_up_via_poll(self):
        from attendance.service import AttendanceService

        user = make_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        since = timezone.now().isoformat()
        AttendanceService().record_entry(emp.pk)

        response = client.get(
            reverse('attendance:list', kwargs={'pk': emp.pk}),
            {'since': since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1

    def test_checkout_on_open_record_is_picked_up_via_update(self):
        import time

        from attendance.service import AttendanceService

        user = make_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        svc = AttendanceService()
        svc.record_entry(emp.pk)

        changed_since = timezone.now().isoformat()
        time.sleep(1.1)  # AttendanceRecord requires exit_time >= entry_time + 1s
        svc.record_exit(emp.pk)

        response = client.get(
            reverse('attendance:list', kwargs={'pk': emp.pk}),
            {'changed_since': changed_since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert body['removed_ids'] == []
        # The re-rendered row must show an actual exit time now, not the
        # muted em-dash placeholder used for still-open records.
        assert '—' not in body['html']

    def test_scoped_to_the_requested_employee_only(self):
        from attendance.service import AttendanceService

        user = make_user()
        emp = make_employee(name='Target Employee')
        other = make_employee(name='Other Employee')
        client = Client()
        client.force_login(user)

        since = timezone.now().isoformat()
        svc = AttendanceService()
        svc.record_entry(emp.pk)
        svc.record_entry(other.pk)

        response = client.get(
            reverse('attendance:list', kwargs={'pk': emp.pk}),
            {'since': since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        body = response.json()
        assert body['count'] == 1

    def test_page_renders_with_live_scripts(self):
        user = make_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('attendance:list', kwargs={'pk': emp.pk}))

        assert response.status_code == 200
        assert b'startLivePoll' in response.content
        assert b'startLiveUpdate' in response.content


@pytest.mark.django_db
class TestAttendanceCalendarLiveUpdate:
    def test_new_checkin_this_month_is_picked_up(self):
        from attendance.service import AttendanceService

        user = make_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        today = timezone.localdate()
        since = timezone.now().isoformat()
        AttendanceService().record_entry(emp.pk)

        response = client.get(
            reverse('attendance_calendar'),
            {'employee': emp.pk, 'year': today.year, 'month': today.month, 'changed_since': since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert today.isoformat() in body['days']
        assert 'em aberto' in body['days'][today.isoformat()]

    def test_checkout_closing_an_open_record_is_picked_up(self):
        import time

        from attendance.service import AttendanceService

        user = make_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        today = timezone.localdate()
        svc = AttendanceService()
        svc.record_entry(emp.pk)

        changed_since = timezone.now().isoformat()
        time.sleep(1.1)
        svc.record_exit(emp.pk)

        response = client.get(
            reverse('attendance_calendar'),
            {'employee': emp.pk, 'year': today.year, 'month': today.month, 'changed_since': changed_since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        body = response.json()
        assert today.isoformat() in body['days']
        assert 'em aberto' not in body['days'][today.isoformat()]

    def test_other_employee_changes_are_not_picked_up(self):
        from attendance.service import AttendanceService

        user = make_user()
        emp = make_employee(name='Watched')
        other = make_employee(name='Not Watched')
        client = Client()
        client.force_login(user)

        today = timezone.localdate()
        since = timezone.now().isoformat()
        AttendanceService().record_entry(other.pk)

        response = client.get(
            reverse('attendance_calendar'),
            {'employee': emp.pk, 'year': today.year, 'month': today.month, 'changed_since': since},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        body = response.json()
        assert body['days'] == {}

    def test_page_renders_with_calendar_live_update_script(self):
        user = make_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('attendance_calendar'), {'employee': emp.pk})

        assert response.status_code == 200
        assert b'startCalendarLiveUpdate' in response.content
        assert b'data-day=' in response.content

    def test_no_employee_selected_does_not_error(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('attendance_calendar'))

        assert response.status_code == 200
        # The shared function definition is always present (base.html);
        # only the per-page CALL is conditional on an employee being picked.
        assert b'startCalendarLiveUpdate({' not in response.content


@pytest.mark.django_db
class TestAttendancePendingReviewView:
    def _make_stale_record(self, emp):
        svc = AttendanceService()
        svc.toggle_for_employee(emp.pk)
        open_rec = svc.get_open_record(emp.pk)
        stale_time = open_rec.entry_time - AttendanceService.MAX_OPEN_DURATION - timedelta(seconds=1)
        AttendanceRecord.objects.filter(pk=open_rec.pk).update(entry_time=stale_time)
        PresenceEvent.objects.filter(attendance_record=open_rec).update(timestamp=stale_time)
        svc.auto_close_if_stale(emp.pk)
        return AttendanceRecord.objects.get(pk=open_rec.pk)

    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('attendance:pending_review'))
        assert response.status_code == 302

    def test_plain_user_is_denied(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('attendance:pending_review'))

        assert response.status_code == 302

    def test_lists_only_auto_closed_open_records(self):
        admin = make_admin_user()
        emp = make_employee(name='Esquecido')
        other_emp = make_employee(name='Em Dia')
        self._make_stale_record(emp)
        AttendanceService().record_entry(other_emp.pk)  # normal open record

        client = Client()
        client.force_login(admin)
        response = client.get(reverse('attendance:pending_review'))

        assert response.status_code == 200
        assert 'Esquecido'.encode() in response.content
        assert 'Em Dia'.encode() not in response.content

    def test_post_sets_exit_time_and_removes_from_pending_list(self):
        admin = make_admin_user()
        emp = make_employee()
        stale = self._make_stale_record(emp)

        client = Client()
        client.force_login(admin)
        exit_time = (stale.entry_time + timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M')
        response = client.post(
            reverse('attendance:pending_review_fix', kwargs={'pk': stale.pk}),
            {'exit_time': exit_time},
        )

        assert response.status_code == 302
        stale.refresh_from_db()
        assert stale.exit_time is not None
        assert stale.auto_closed is True  # kept as audit trail

        response = client.get(reverse('attendance:pending_review'))
        assert list(response.context['records']) == []

    def test_post_invalid_exit_time_shows_error_and_keeps_record_open(self):
        admin = make_admin_user()
        emp = make_employee()
        stale = self._make_stale_record(emp)

        client = Client()
        client.force_login(admin)
        response = client.post(
            reverse('attendance:pending_review_fix', kwargs={'pk': stale.pk}),
            {'exit_time': 'not-a-date'},
            follow=True,
        )

        assert response.status_code == 200
        stale.refresh_from_db()
        assert stale.exit_time is None
