from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from accounts.models import UserProfile
from employees.models import Employee
from trucks.models import Truck, TruckAssignment, TruckBrand, TruckModel


def make_user():
    user = User.objects.create_user(username='plain', password='pass')
    user.profile.role = UserProfile.SIMPLE
    user.profile.save()
    return user


def make_truck_model(brand_name='Volvo', model_name='FH'):
    brand, _ = TruckBrand.objects.get_or_create(name=brand_name)
    truck_model, _ = TruckModel.objects.get_or_create(brand=brand, name=model_name)
    return truck_model


def make_employee(**kw):
    defaults = dict(name='Driver', role='Motorista', hire_date=date(2020, 1, 1), is_driver=True)
    defaults.update(kw)
    return Employee.objects.create(**defaults)


@pytest.mark.django_db
class TestTruckListQueryCount:
    def test_query_count_does_not_scale_with_truck_count(self):
        """Regression for the N+1 in TruckListView: listing N trucks (each
        with a driver assigned) must not issue ~2 extra queries per truck."""
        user = make_user()
        client = Client()
        client.force_login(user)

        truck_model = make_truck_model()
        for i in range(10):
            truck = Truck.objects.create(
                license_plate=f'ABC{i % 10}D{i:02d}', truck_model=truck_model,
                color='branca', chassis=f'CHASSIS{i:010d}', year=2020,
            )
            driver = make_employee(name=f'Driver {i}')
            TruckAssignment.objects.create(truck=truck, driver=driver)

        with CaptureQueriesContext(connection) as small:
            client.get(reverse('trucks:list'))
        small_count = len(small.captured_queries)

        for i in range(10, 30):
            truck = Truck.objects.create(
                license_plate=f'XYZ{i % 10}D{i:02d}', truck_model=truck_model,
                color='azul', chassis=f'CHASSIS{i:010d}', year=2021,
            )
            driver = make_employee(name=f'Driver {i}')
            TruckAssignment.objects.create(truck=truck, driver=driver)

        with CaptureQueriesContext(connection) as large:
            client.get(reverse('trucks:list'))
        large_count = len(large.captured_queries)

        # Both requests render one page of PAGE_SIZE=20 trucks, so the query
        # count should be flat regardless of total truck count in the DB.
        assert large_count == small_count
