"""Unit tests for the Employee model (task 9.1)."""
import pytest
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from employees.models import Employee


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
        from trucks.models import Truck, TruckAssignment, TruckBrand, TruckModel

        emp = make_employee(is_driver=True)
        brand, _ = TruckBrand.objects.get_or_create(name="Volvo")
        truck_model, _ = TruckModel.objects.get_or_create(brand=brand, name="FH")
        truck = Truck.objects.create(
            license_plate="ABC1234",
            truck_model=truck_model,
            color="branca",
            chassis="12345678901234567",
            year=2020,
        )
        TruckAssignment.objects.create(truck=truck, driver=emp)
        count_before = TruckAssignment.objects.filter(driver=emp).count()

        Employee.objects.filter(pk=emp.pk).update(is_active=False)

        assert TruckAssignment.objects.filter(driver=emp).count() == count_before
