"""
Unit tests for EmployeeListView's "Histórico de Entradas" sidebar widget:
shows 15 recent presence events with infinite-scroll continuation for the rest.
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from attendance.models import PresenceEvent
from biometric.exceptions import BiometricDeviceNotFoundError
from biometric.models import BiometricEnrollRequest, BiometricTemplate
from employees.models import Employee


def make_user():
    return User.objects.create_user(username="admin", password="pass")


def make_admin_user():
    # EmployeeEnrollView requires role admin/master (EditRequiredMixin);
    # is_superuser maps to role 'master' (accounts.mixins.get_role).
    return User.objects.create_user(username="boss", password="pass", is_superuser=True)


def make_employee(**kw):
    defaults = dict(name="Test Employee", role="Op", hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_presence_events(employee, count, start_minutes_ago=0):
    """Create `count` alternating IN/OUT events, most recent first in creation order."""
    now = timezone.now()
    events = []
    for i in range(count):
        direction = PresenceEvent.IN if i % 2 == 0 else PresenceEvent.OUT
        ts = now - timedelta(minutes=start_minutes_ago + i)
        events.append(PresenceEvent(employee=employee, direction=direction, timestamp=ts))
    PresenceEvent.objects.bulk_create(events)


@pytest.mark.django_db
class TestEmployeeListHistoryWidget:
    def test_shows_at_most_15_events(self):
        user = make_user()
        emp = make_employee()
        make_presence_events(emp, 20)

        client = Client()
        client.force_login(user)
        response = client.get(reverse('employees:list'))

        assert response.status_code == 200
        assert len(response.context['recent_presence_events']) == 15
        assert response.context['recent_presence_has_next'] is True

    def test_has_next_false_when_15_or_fewer(self):
        user = make_user()
        emp = make_employee()
        make_presence_events(emp, 10)

        client = Client()
        client.force_login(user)
        response = client.get(reverse('employees:list'))

        assert len(response.context['recent_presence_events']) == 10
        assert response.context['recent_presence_has_next'] is False

    def test_continuation_via_presence_history_matches_remaining_events(self):
        """
        The sidebar's "load more" hits presence_history?type=employees&compact=1&
        page_size=15&page=2 — confirm it picks up exactly where the inline 15 left off.
        """
        user = make_user()
        emp = make_employee()
        make_presence_events(emp, 20)

        client = Client()
        client.force_login(user)

        first_page = client.get(reverse('employees:list'))
        first_15_timestamps = {e.timestamp for e in first_page.context['recent_presence_events']}

        response = client.get(
            reverse('presence_history'),
            {'type': 'employees', 'compact': '1', 'page_size': '15', 'page': '2'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert response.status_code == 200
        body = response.json()
        assert body['has_next'] is False

        # Exactly the remaining 5 events, none overlapping with the first 15.
        all_timestamps = set(
            PresenceEvent.objects.filter(employee=emp).values_list('timestamp', flat=True)
        )
        remaining_expected = all_timestamps - first_15_timestamps
        assert len(remaining_expected) == 5
        # The compact partial renders the employee's name once per row.
        assert body['html'].count(emp.name) == 5


@pytest.mark.django_db
class TestEmployeeEnrollViewRemoteQueue:
    """
    When no local reader is found (always true on a server with no hardware
    attached, e.g. the VPS), EmployeeEnrollView.post() now queues a
    BiometricEnrollRequest for a remote kiosk instead of just erroring out.
    """

    def _post_capture(self, client, employee):
        with patch("employees.views.BiometricService") as mock_service_cls:
            mock_service_cls.return_value = MagicMock(
                connect=MagicMock(side_effect=BiometricDeviceNotFoundError("no reader")),
            )
            return client.post(reverse('employees:enroll', kwargs={'pk': employee.pk}))

    def test_no_local_reader_creates_pending_request(self):
        user = make_admin_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        response = self._post_capture(client, emp)

        assert response.status_code == 200  # re-rendered waiting state, no redirect
        assert response.context['pending_request'] is not None
        req = BiometricEnrollRequest.objects.get(employee=emp)
        assert req.status == BiometricEnrollRequest.PENDING
        assert req.requested_by == user

    def test_second_click_does_not_duplicate_pending_request(self):
        user = make_admin_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        self._post_capture(client, emp)
        self._post_capture(client, emp)

        assert BiometricEnrollRequest.objects.filter(employee=emp).count() == 1

    def test_ajax_get_reports_waiting_while_pending(self):
        user = make_admin_user()
        emp = make_employee()
        BiometricEnrollRequest.objects.create(employee=emp, requested_by=user)
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('employees:enroll', kwargs={'pk': emp.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['waiting'] is True
        assert body['has_biometric'] is False

    def test_ajax_get_reports_not_waiting_once_fulfilled(self):
        user = make_admin_user()
        emp = make_employee()
        req = BiometricEnrollRequest.objects.create(employee=emp, requested_by=user)
        req.mark_done()
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('employees:enroll', kwargs={'pk': emp.pk}), HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.json()['waiting'] is False

    def test_cancel_marks_request_cancelled_and_stops_waiting(self):
        user = make_admin_user()
        emp = make_employee()
        BiometricEnrollRequest.objects.create(employee=emp, requested_by=user)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('employees:enroll', kwargs={'pk': emp.pk}), {'action': 'cancel'},
        )

        assert response.status_code == 302
        req = BiometricEnrollRequest.objects.get(employee=emp)
        assert req.status == BiometricEnrollRequest.CANCELLED
        follow = client.get(reverse('employees:enroll', kwargs={'pk': emp.pk}))
        assert follow.context['pending_request'] is None


@pytest.mark.django_db
class TestEmployeeDeleteBiometricView:
    def test_deletes_existing_template_and_redirects_to_edit(self):
        user = make_admin_user()
        emp = make_employee()
        BiometricTemplate.objects.create(employee=emp, template=b'x' * 64)
        client = Client()
        client.force_login(user)

        response = client.post(reverse('employees:biometric_delete', kwargs={'pk': emp.pk}))

        assert response.status_code == 302
        assert response.url == reverse('employees:update', kwargs={'pk': emp.pk})
        assert not BiometricTemplate.objects.filter(employee=emp).exists()

    def test_cancels_pending_remote_request_too(self):
        user = make_admin_user()
        emp = make_employee()
        BiometricTemplate.objects.create(employee=emp, template=b'x' * 64)
        req = BiometricEnrollRequest.objects.create(employee=emp)
        client = Client()
        client.force_login(user)

        client.post(reverse('employees:biometric_delete', kwargs={'pk': emp.pk}))

        req.refresh_from_db()
        assert req.status == BiometricEnrollRequest.CANCELLED

    def test_no_existing_template_is_a_no_op(self):
        user = make_admin_user()
        emp = make_employee()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('employees:biometric_delete', kwargs={'pk': emp.pk}))

        assert response.status_code == 302

    def test_requires_admin_role(self):
        user = make_user()  # no is_superuser → role 'simple', below EditRequiredMixin's allowed_roles
        emp = make_employee()
        BiometricTemplate.objects.create(employee=emp, template=b'x' * 64)
        client = Client()
        client.force_login(user)

        client.post(reverse('employees:biometric_delete', kwargs={'pk': emp.pk}))

        assert BiometricTemplate.objects.filter(employee=emp).exists()
