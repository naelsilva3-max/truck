from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from attendance.models import PresenceEvent
from employees.models import Employee


def make_user():
    return User.objects.create_user(username='plain', password='pass')


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
