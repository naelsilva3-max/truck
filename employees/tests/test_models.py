"""Unit tests for Employee and BiometricTemplate models (tasks 9.1 and 9.2)."""
import pytest
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from employees.models import BiometricTemplate, Employee


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_employee(**kwargs) -> Employee:
    defaults = dict(name="João Silva", role="Operador", hire_date=date(2020, 1, 1))
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


# ---------------------------------------------------------------------------
# 9.1 Employee model validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEmployeeModel:

    def test_valid_employee_is_created(self):
        emp = make_employee()
        assert emp.pk is not None
        assert emp.name == "João Silva"

    def test_blank_name_raises(self):
        with pytest.raises(ValidationError):
            make_employee(name="")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(ValidationError):
            make_employee(name="   ")

    def test_future_hire_date_raises(self):
        with pytest.raises(ValidationError):
            make_employee(hire_date=date.today() + timedelta(days=1))

    def test_today_hire_date_is_accepted(self):
        emp = make_employee(hire_date=date.today())
        assert emp.hire_date == date.today()

    def test_deactivate_preserves_attendance_records(self):
        from attendance.models import AttendanceRecord
        from django.utils import timezone

        emp = make_employee()
        now = timezone.now()
        AttendanceRecord.objects.create(
            employee=emp,
            entry_time=now,
            date=now.date(),
        )
        count_before = AttendanceRecord.objects.filter(employee=emp).count()

        Employee.objects.filter(pk=emp.pk).update(is_active=False)

        assert AttendanceRecord.objects.filter(employee=emp).count() == count_before

    def test_deactivate_preserves_truck_assignments(self):
        from trucks.models import Truck, TruckAssignment

        emp = make_employee(is_driver=True)
        truck = Truck.objects.create(
            license_plate="ABC1234",
            model="Volvo FH",
            color="Branco",
            chassis="12345678901234567",
            year=2020,
        )
        TruckAssignment.objects.create(truck=truck, driver=emp)
        count_before = TruckAssignment.objects.filter(driver=emp).count()

        Employee.objects.filter(pk=emp.pk).update(is_active=False)

        assert TruckAssignment.objects.filter(driver=emp).count() == count_before


# ---------------------------------------------------------------------------
# 9.2 BiometricTemplate model validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBiometricTemplateModel:

    def test_zero_bytes_raises(self):
        emp = make_employee()
        with pytest.raises(ValidationError):
            BiometricTemplate.objects.create(employee=emp, template=b"")

    def test_over_10kb_raises(self):
        emp = make_employee()
        with pytest.raises(ValidationError):
            BiometricTemplate.objects.create(employee=emp, template=b"x" * 10_241)

    def test_valid_template_is_saved(self):
        emp = make_employee()
        bt = BiometricTemplate.objects.create(employee=emp, template=b"x" * 512)
        assert bt.pk is not None

    def test_reenroll_replaces_existing_template(self):
        emp = make_employee()
        BiometricTemplate.objects.create(employee=emp, template=b"old" * 10)
        # upsert: replace via get_or_create pattern used in enrollment view
        bt, created = BiometricTemplate.objects.get_or_create(
            employee=emp, defaults={"template": b"new" * 10}
        )
        if not created:
            bt.template = b"new" * 10
            bt.save()
        assert BiometricTemplate.objects.filter(employee=emp).count() == 1
        assert bytes(BiometricTemplate.objects.get(employee=emp).template) == b"new" * 10
