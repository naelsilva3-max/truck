import json
import time
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from attendance.service import AttendanceService
from employees.models import Employee


def make_user():
    return User.objects.create_user(username='watcher', password='pass')


def make_employee(**kw):
    defaults = dict(name='Kiosk Employee', role='Op', hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


@pytest.mark.django_db
def test_sequential_in_then_out_polling_simulates_browser():
    """Regression: walks through the exact sequence the browser's
    startLivePoll performs (poll, advance cursor to `data.newest`, poll
    again) across an IN event followed by an OUT event, to make sure
    exit/checkout events aren't silently dropped by the polling endpoint."""
    user = make_user()
    emp = make_employee()
    client = Client()
    client.force_login(user)

    since = timezone.now().isoformat()

    svc = AttendanceService()
    svc.record_entry(emp.pk)

    r1 = client.get(
        reverse('presence_history'),
        {'type': 'employees', 'compact': '1', 'since': since},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest',
    )
    body1 = json.loads(r1.content)
    assert body1['count'] == 1
    assert 'Entrada' in body1['html']

    # Browser advances its cursor to data.newest, as the real JS does.
    since = body1['newest']

    time.sleep(1.1)  # AttendanceRecord requires exit_time >= entry_time + 1s
    svc.record_exit(emp.pk)

    r2 = client.get(
        reverse('presence_history'),
        {'type': 'employees', 'compact': '1', 'since': since},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest',
    )
    body2 = json.loads(r2.content)
    assert body2['count'] == 1
    assert 'Saída' in body2['html']
