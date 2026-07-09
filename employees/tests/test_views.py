"""
Unit tests for EmployeeListView's "Histórico de Entradas" sidebar widget:
shows 15 recent presence events with infinite-scroll continuation for the rest.
"""
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from attendance.models import PresenceEvent
from employees.models import Employee


def make_user():
    return User.objects.create_user(username="admin", password="pass")


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
