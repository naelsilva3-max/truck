"""
Integration tests for the kiosk-facing JSON API (biometric/api_views.py),
exercised through the Django test client.
"""
import base64
import json
from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from attendance.models import AttendanceRecord
from biometric.models import BiometricEnrollRequest, BiometricTemplate, KioskDevice
from employees.models import Employee


def make_employee(**kw) -> Employee:
    defaults = dict(name="Test", role="Op", hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def _auth_headers(raw_token: str) -> dict:
    return {'HTTP_AUTHORIZATION': f'Bearer {raw_token}'}


@pytest.fixture
def device():
    _, raw_token = KioskDevice.issue(name="Quiosque Teste")
    return raw_token


@pytest.mark.django_db
class TestKioskEnrollView:
    def _post(self, client, raw_token, payload):
        return client.post(
            reverse('biometric:api_enroll'),
            data=json.dumps(payload),
            content_type='application/json',
            **_auth_headers(raw_token),
        )

    def test_requires_auth(self):
        client = Client()
        response = client.post(
            reverse('biometric:api_enroll'), data=json.dumps({}), content_type='application/json',
        )
        assert response.status_code == 401

    def test_creates_new_template(self, device):
        emp = make_employee()
        client = Client()
        template_b64 = base64.b64encode(b'x' * 64).decode()

        response = self._post(client, device, {'employee_id': emp.pk, 'template_b64': template_b64})

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'ok'
        assert body['created'] is True
        bt = BiometricTemplate.objects.get(employee=emp)
        assert bytes(bt.template) == b'x' * 64

    def test_updates_existing_template(self, device):
        emp = make_employee()
        BiometricTemplate.objects.create(employee=emp, template=b'old' * 20)
        client = Client()
        new_template_b64 = base64.b64encode(b'new' * 20).decode()

        response = self._post(client, device, {'employee_id': emp.pk, 'template_b64': new_template_b64})

        assert response.status_code == 200
        assert response.json()['created'] is False
        bt = BiometricTemplate.objects.get(employee=emp)
        assert bytes(bt.template) == b'new' * 20

    def test_unknown_employee_returns_404(self, device):
        client = Client()
        response = self._post(
            client, device, {'employee_id': 999999, 'template_b64': base64.b64encode(b'x' * 8).decode()},
        )
        assert response.status_code == 404

    def test_malformed_payload_returns_400(self, device):
        client = Client()
        response = self._post(client, device, {'employee_id': 'not-an-int'})
        assert response.status_code == 400

    def test_oversized_template_returns_400(self, device):
        emp = make_employee()
        client = Client()
        oversized_b64 = base64.b64encode(b'x' * 20_000).decode()  # > 10KB model limit
        response = self._post(client, device, {'employee_id': emp.pk, 'template_b64': oversized_b64})
        assert response.status_code == 400

    def test_enroll_request_id_closes_that_specific_request(self, device):
        emp = make_employee()
        req = BiometricEnrollRequest.objects.create(employee=emp)
        other_req = BiometricEnrollRequest.objects.create(employee=make_employee(name="Outro"))
        client = Client()

        response = self._post(client, device, {
            'employee_id': emp.pk,
            'template_b64': base64.b64encode(b'x' * 64).decode(),
            'enroll_request_id': req.pk,
        })

        assert response.status_code == 200
        req.refresh_from_db()
        assert req.status == BiometricEnrollRequest.DONE
        assert req.completed_at is not None
        assert req.fulfilled_by_device is not None
        other_req.refresh_from_db()
        assert other_req.status == BiometricEnrollRequest.PENDING

    def test_without_enroll_request_id_closes_oldest_pending_for_employee(self, device):
        emp = make_employee()
        req = BiometricEnrollRequest.objects.create(employee=emp)
        client = Client()

        response = self._post(client, device, {
            'employee_id': emp.pk,
            'template_b64': base64.b64encode(b'x' * 64).decode(),
        })

        assert response.status_code == 200
        req.refresh_from_db()
        assert req.status == BiometricEnrollRequest.DONE

    def test_enroll_request_id_already_closed_is_a_no_op(self, device):
        emp = make_employee()
        req = BiometricEnrollRequest.objects.create(employee=emp)
        req.mark_cancelled()
        client = Client()

        response = self._post(client, device, {
            'employee_id': emp.pk,
            'template_b64': base64.b64encode(b'x' * 64).decode(),
            'enroll_request_id': req.pk,
        })

        assert response.status_code == 200
        req.refresh_from_db()
        assert req.status == BiometricEnrollRequest.CANCELLED  # untouched, not re-opened/closed
        assert BiometricTemplate.objects.filter(employee=emp).exists()


@pytest.mark.django_db
class TestKioskEnrollRequestNextView:
    def test_requires_auth(self):
        client = Client()
        response = client.get(reverse('biometric:api_enroll_requests_next'))
        assert response.status_code == 401

    def test_no_pending_requests(self, device):
        client = Client()
        response = client.get(reverse('biometric:api_enroll_requests_next'), **_auth_headers(device))
        assert response.status_code == 200
        assert response.json() == {'has_pending': False}

    def test_returns_pending_request_fields(self, device):
        emp = make_employee(name="Fulano")
        req = BiometricEnrollRequest.objects.create(employee=emp)
        client = Client()

        response = client.get(reverse('biometric:api_enroll_requests_next'), **_auth_headers(device))

        assert response.status_code == 200
        body = response.json()
        assert body['has_pending'] is True
        assert body['request_id'] == req.pk
        assert body['employee_id'] == emp.pk
        assert body['employee_name'] == "Fulano"

    def test_returns_oldest_pending_when_multiple(self, device):
        emp1 = make_employee(name="Primeiro")
        emp2 = make_employee(name="Segundo")
        older = BiometricEnrollRequest.objects.create(employee=emp1)
        BiometricEnrollRequest.objects.filter(pk=older.pk).update(
            requested_at=older.requested_at - timedelta(minutes=5)
        )
        BiometricEnrollRequest.objects.create(employee=emp2)
        client = Client()

        response = client.get(reverse('biometric:api_enroll_requests_next'), **_auth_headers(device))

        assert response.json()['request_id'] == older.pk

    def test_ignores_done_and_cancelled_requests(self, device):
        emp = make_employee()
        done = BiometricEnrollRequest.objects.create(employee=emp)
        done.mark_done()
        cancelled = BiometricEnrollRequest.objects.create(employee=emp)
        cancelled.mark_cancelled()
        client = Client()

        response = client.get(reverse('biometric:api_enroll_requests_next'), **_auth_headers(device))

        assert response.json() == {'has_pending': False}


@pytest.mark.django_db
class TestKioskTemplateSyncView:
    def test_requires_auth(self):
        client = Client()
        response = client.get(reverse('biometric:api_templates'))
        assert response.status_code == 401

    def test_returns_only_active_employees_templates(self, device):
        active_emp = make_employee(name="Ativo")
        inactive_emp = make_employee(name="Inativo", is_active=False)
        BiometricTemplate.objects.create(employee=active_emp, template=b'a' * 32)
        BiometricTemplate.objects.create(employee=inactive_emp, template=b'b' * 32)

        client = Client()
        response = client.get(reverse('biometric:api_templates'), **_auth_headers(device))

        assert response.status_code == 200
        body = response.json()
        emp_ids = {row['employee_id'] for row in body['templates']}
        assert emp_ids == {active_emp.pk}
        assert body['count'] == 1

    def test_empty_when_no_templates_enrolled(self, device):
        client = Client()
        response = client.get(reverse('biometric:api_templates'), **_auth_headers(device))
        assert response.status_code == 200
        assert response.json()['templates'] == []


@pytest.mark.django_db
class TestKioskScanReportView:
    def _post(self, client, raw_token, employee_id):
        return client.post(
            reverse('biometric:api_scan'),
            data=json.dumps({'employee_id': employee_id}),
            content_type='application/json',
            **_auth_headers(raw_token),
        )

    def test_requires_auth(self):
        client = Client()
        response = client.post(
            reverse('biometric:api_scan'), data=json.dumps({'employee_id': 1}), content_type='application/json',
        )
        assert response.status_code == 401

    def test_first_scan_records_entry(self, device):
        emp = make_employee()
        client = Client()
        response = self._post(client, device, emp.pk)
        assert response.status_code == 200
        body = response.json()
        assert body['direction'] == 'IN'

    def test_second_scan_records_exit(self, device):
        emp = make_employee()
        client = Client()
        self._post(client, device, emp.pk)
        # Backdate the entry so exit_time's "at least 1s after entry_time"
        # model validation is satisfied (mirrors attendance/tests/test_service.py).
        open_rec = AttendanceRecord.objects.get(employee=emp, exit_time__isnull=True)
        AttendanceRecord.objects.filter(pk=open_rec.pk).update(
            entry_time=open_rec.entry_time - timedelta(seconds=2)
        )
        response = self._post(client, device, emp.pk)
        assert response.status_code == 200
        assert response.json()['direction'] == 'OUT'

    def test_unknown_employee_returns_404(self, device):
        client = Client()
        response = self._post(client, device, 999999)
        assert response.status_code == 404

    def test_inactive_employee_returns_409(self, device):
        emp = make_employee(is_active=False)
        client = Client()
        response = self._post(client, device, emp.pk)
        assert response.status_code == 409

    def test_malformed_payload_returns_400(self, device):
        client = Client()
        response = client.post(
            reverse('biometric:api_scan'),
            data=json.dumps({}),
            content_type='application/json',
            **_auth_headers(device),
        )
        assert response.status_code == 400
