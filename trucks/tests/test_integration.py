"""Integration tests (tasks 11.1, 11.2, 11.3)."""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from accounts.models import UserProfile
from attendance.models import AttendanceRecord
from attendance.service import AttendanceService
from biometric.models import BiometricTemplate
from employees.models import Employee
from trucks.models import Truck, TruckAssignment, TruckBrand, TruckModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user():
    """A logged-in user with elevated (master) role — these flows all touch
    edit-gated views (employee create/enroll, truck assignment)."""
    user = User.objects.create_user(username="admin", password="pass")
    user.profile.role = UserProfile.MASTER
    user.profile.save()
    return user


def make_employee(**kw):
    defaults = dict(name="Test Employee", role="Op", hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_truck_model(brand_name="Volvo", model_name="FH"):
    brand, _ = TruckBrand.objects.get_or_create(name=brand_name)
    truck_model, _ = TruckModel.objects.get_or_create(brand=brand, name=model_name)
    return truck_model


def make_truck(**kw):
    defaults = dict(
        license_plate="ABC1D23", truck_model=make_truck_model(),
        color="branca", chassis="12345678901234567", year=2020,
    )
    defaults.update(kw)
    return Truck.objects.create(**defaults)


# ---------------------------------------------------------------------------
# 11.1 Full employee enrollment flow
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnrollmentFlow:

    def test_create_employee_redirects_to_enroll(self):
        user = make_user()
        client = Client()
        client.login(username="admin", password="pass")

        response = client.post("/employees/new/", {
            "name": "Maria Silva",
            "role": "Operadora",
            "hire_date": "2022-01-01",
            "is_driver": False,
            "is_active": True,
        })
        assert response.status_code == 302
        emp = Employee.objects.get(name="Maria Silva")
        assert f"/employees/{emp.pk}/enroll/" in response["Location"]

    def test_enroll_creates_biometric_template(self):
        user = make_user()
        emp = make_employee()
        client = Client()
        client.login(username="admin", password="pass")

        dummy_template = b"\xab" * 512

        mock_service = MagicMock()
        mock_service.connect.return_value = True
        mock_service.capture_registration.return_value = dummy_template
        mock_service.is_connected = True

        with patch("employees.views.BiometricService", return_value=mock_service):
            response = client.post(f"/employees/{emp.pk}/enroll/")

        assert BiometricTemplate.objects.filter(employee=emp).exists()
        bt = BiometricTemplate.objects.get(employee=emp)
        assert bytes(bt.template) == dummy_template

    def test_enroll_shows_success_message(self):
        user = make_user()
        emp = make_employee()
        client = Client()
        client.login(username="admin", password="pass")

        mock_service = MagicMock()
        mock_service.connect.return_value = True
        mock_service.capture_registration.return_value = b"\xcd" * 256
        mock_service.is_connected = True

        with patch("employees.views.BiometricService", return_value=mock_service):
            response = client.post(f"/employees/{emp.pk}/enroll/", follow=True)

        messages = [str(m) for m in response.context["messages"]]
        assert any("sucesso" in m.lower() or "biometria" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# 11.2 Biometric event triggers attendance toggle
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBiometricAttendanceToggle:

    def test_first_event_creates_entry(self):
        emp = make_employee()
        template_bytes = b"t" * 64
        BiometricTemplate.objects.create(employee=emp, template=template_bytes)

        mock_bio = MagicMock()
        mock_bio.identify.return_value = emp.pk
        svc = AttendanceService(biometric_service=mock_bio)

        rec = svc.process_biometric_event(template_bytes)

        assert rec is not None
        assert rec.exit_time is None
        assert rec.employee_id == emp.pk

    def test_second_event_closes_record(self):
        emp = make_employee()
        template_bytes = b"t" * 64
        BiometricTemplate.objects.create(employee=emp, template=template_bytes)

        mock_bio = MagicMock()
        mock_bio.identify.return_value = emp.pk
        svc = AttendanceService(biometric_service=mock_bio)

        # First event: entry
        rec = svc.process_biometric_event(template_bytes)
        # Backdate entry to ensure valid exit
        AttendanceRecord.objects.filter(pk=rec.pk).update(
            entry_time=rec.entry_time - timedelta(seconds=5)
        )

        # Second event: exit
        rec2 = svc.process_biometric_event(template_bytes)

        assert rec2.exit_time is not None
        assert rec2.exit_time > rec2.entry_time
        assert rec2.pk == rec.pk


# ---------------------------------------------------------------------------
# 11.3 Full truck assignment flow
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTruckAssignmentFlow:

    def test_assign_driver_creates_active_assignment(self):
        user = make_user()
        driver = make_employee(is_driver=True)
        truck = make_truck()
        client = Client()
        client.login(username="admin", password="pass")

        response = client.post(f"/trucks/{truck.pk}/assign/", {
            "driver": driver.pk,
            "notes": "",
        })
        assert response.status_code == 302
        assert TruckAssignment.objects.filter(
            truck=truck, driver=driver, unassigned_at__isnull=True
        ).exists()

    def test_second_assign_to_same_truck_is_rejected(self):
        user = make_user()
        driver1 = make_employee(name="Driver1", is_driver=True)
        driver2 = make_employee(name="Driver2", is_driver=True)
        truck = make_truck()
        client = Client()
        client.login(username="admin", password="pass")

        client.post(f"/trucks/{truck.pk}/assign/", {"driver": driver1.pk, "notes": ""})

        client.post(f"/trucks/{truck.pk}/assign/", {"driver": driver2.pk, "notes": ""})

        # Only one active assignment should exist
        active = TruckAssignment.objects.filter(
            truck=truck, unassigned_at__isnull=True
        )
        assert active.count() == 1

    def test_unassign_sets_unassigned_at(self):
        user = make_user()
        driver = make_employee(is_driver=True)
        truck = make_truck()
        TruckAssignment.objects.create(truck=truck, driver=driver)
        client = Client()
        client.login(username="admin", password="pass")

        response = client.post(f"/trucks/{truck.pk}/unassign/")
        assert response.status_code == 302

        assignment = TruckAssignment.objects.get(truck=truck, driver=driver)
        assert assignment.unassigned_at is not None

    def test_reassign_after_unassign_succeeds(self):
        user = make_user()
        driver1 = make_employee(name="OldDriver", is_driver=True)
        driver2 = make_employee(name="NewDriver", is_driver=True)
        truck = make_truck()
        client = Client()
        client.login(username="admin", password="pass")

        client.post(f"/trucks/{truck.pk}/assign/", {"driver": driver1.pk, "notes": ""})
        client.post(f"/trucks/{truck.pk}/unassign/")
        client.post(f"/trucks/{truck.pk}/assign/", {"driver": driver2.pk, "notes": ""})

        active = TruckAssignment.objects.filter(
            truck=truck, driver=driver2, unassigned_at__isnull=True
        )
        assert active.exists()
