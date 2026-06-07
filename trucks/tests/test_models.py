"""Unit tests for Truck and TruckAssignment models (tasks 9.4 and 9.5)."""
import pytest
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from employees.models import Employee
from trucks.models import Truck, TruckAssignment
from trucks.views import get_current_driver


def make_employee(**kw) -> Employee:
    defaults = dict(name="Motorista", role="Driver", hire_date=date(2020, 1, 1), is_driver=True)
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_truck(**kw) -> Truck:
    defaults = dict(
        license_plate="ABC1D23",
        model="Volvo FH",
        color="Branco",
        chassis="12345678901234567",
        year=2020,
    )
    defaults.update(kw)
    return Truck.objects.create(**defaults)


# ---------------------------------------------------------------------------
# 9.4 Truck model validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTruckModel:

    def test_mercosul_plate_accepted(self):
        t = make_truck(license_plate="ABC1D23", chassis="AAAAAAAAAAAAAAAAA")
        assert t.license_plate == "ABC1D23"

    def test_old_format_plate_accepted(self):
        t = make_truck(license_plate="ABC1234", chassis="BBBBBBBBBBBBBBBBB")
        assert t.license_plate == "ABC1234"

    def test_invalid_plate_raises(self):
        with pytest.raises(ValidationError):
            make_truck(license_plate="INVALID1", chassis="CCCCCCCCCCCCCCCCC")

    def test_chassis_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            make_truck(license_plate="DEF2E34", chassis="SHORT")

    def test_chassis_non_alphanumeric_raises(self):
        with pytest.raises(ValidationError):
            make_truck(license_plate="GHI3F45", chassis="1234567890123456!")

    def test_duplicate_plate_raises(self):
        make_truck(license_plate="JKL4G56", chassis="DDDDDDDDDDDDDDDDD")
        with pytest.raises((ValidationError, IntegrityError)):
            make_truck(license_plate="JKL4G56", chassis="EEEEEEEEEEEEEEEEE")

    def test_duplicate_chassis_raises(self):
        make_truck(license_plate="MNO5H67", chassis="FFFFFFFFFFFFFFFFFFF"[:17])
        with pytest.raises((ValidationError, IntegrityError)):
            make_truck(license_plate="PQR6I78", chassis="FFFFFFFFFFFFFFFFFFF"[:17])

    def test_year_before_1900_raises(self):
        with pytest.raises(ValidationError):
            make_truck(license_plate="STU7J89", chassis="GGGGGGGGGGGGGGGGG", year=1899)

    def test_year_after_current_raises(self):
        future_year = date.today().year + 1
        with pytest.raises(ValidationError):
            make_truck(license_plate="VWX8K90", chassis="HHHHHHHHHHHHHHHHH", year=future_year)

    def test_physical_delete_raises(self):
        t = make_truck(license_plate="YZA9L01", chassis="IIIIIIIIIIIIIIIII")
        with pytest.raises(PermissionError):
            t.delete()

    def test_plate_normalized_to_uppercase(self):
        t = make_truck(license_plate="abc1d23", chassis="JJJJJJJJJJJJJJJJJ")
        assert t.license_plate == "ABC1D23"


# ---------------------------------------------------------------------------
# 9.5 TruckAssignment validation and TruckManager
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTruckAssignment:

    def test_non_driver_raises(self):
        emp = make_employee(is_driver=False)
        truck = make_truck(license_plate="AAA1B23", chassis="KKKKKKKKKKKKKKKKK")
        with pytest.raises(ValidationError):
            TruckAssignment.objects.create(truck=truck, driver=emp)

    def test_second_active_driver_raises(self):
        driver1 = make_employee(name="Driver1")
        driver2 = make_employee(name="Driver2")
        truck = make_truck(license_plate="BBB2C34", chassis="LLLLLLLLLLLLLLLLL")
        TruckAssignment.objects.create(truck=truck, driver=driver1)
        with pytest.raises(ValidationError):
            TruckAssignment.objects.create(truck=truck, driver=driver2)

    def test_get_current_driver_returns_driver(self):
        driver = make_employee()
        truck = make_truck(license_plate="CCC3D45", chassis="MMMMMMMMMMMMMMMMM")
        TruckAssignment.objects.create(truck=truck, driver=driver)
        assert get_current_driver(truck.pk) == driver

    def test_get_current_driver_returns_none_when_no_active(self):
        truck = make_truck(license_plate="DDD4E56", chassis="NNNNNNNNNNNNNNNNN")
        assert get_current_driver(truck.pk) is None

    def test_unassigned_at_before_assigned_at_raises(self):
        from django.utils import timezone
        driver = make_employee()
        truck = make_truck(license_plate="EEE5F67", chassis="OOOOOOOOOOOOOOOOO")
        now = timezone.now()
        with pytest.raises(ValidationError):
            TruckAssignment.objects.create(
                truck=truck,
                driver=driver,
                assigned_at=now,
                unassigned_at=now - __import__("datetime").timedelta(seconds=1),
            )

    def test_physical_delete_raises(self):
        driver = make_employee()
        truck = make_truck(license_plate="FFF6G78", chassis="PPPPPPPPPPPPPPPPP")
        assignment = TruckAssignment.objects.create(truck=truck, driver=driver)
        with pytest.raises(PermissionError):
            assignment.delete()


# ---------------------------------------------------------------------------
# 9.6 Security constraints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSecurityConstraints:

    def test_attendance_record_physical_delete_raises(self):
        from attendance.models import AttendanceRecord
        from django.utils import timezone

        emp = make_employee()
        now = timezone.now()
        rec = AttendanceRecord.objects.create(
            employee=emp, entry_time=now, date=now.date()
        )
        with pytest.raises(PermissionError):
            rec.delete()

    def test_truck_assignment_physical_delete_raises(self):
        driver = make_employee()
        truck = make_truck(license_plate="GGG7H89", chassis="QQQQQQQQQQQQQQQQQ")
        assignment = TruckAssignment.objects.create(truck=truck, driver=driver)
        with pytest.raises(PermissionError):
            assignment.delete()

    def test_unauthenticated_employee_list_redirects(self):
        from django.test import Client
        client = Client()
        response = client.get("/employees/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_unauthenticated_truck_list_redirects(self):
        from django.test import Client
        client = Client()
        response = client.get("/trucks/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_unauthenticated_attendance_redirects(self):
        from django.test import Client
        emp = make_employee()
        client = Client()
        response = client.get(f"/employees/{emp.pk}/attendance/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]
