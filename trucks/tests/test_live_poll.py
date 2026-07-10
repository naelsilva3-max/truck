from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from trucks.models import Truck, TruckBrand, TruckModel


def make_user():
    return User.objects.create_user(username='plain', password='pass')


def make_truck_model(brand_name='Volvo', model_name='FH'):
    brand, _ = TruckBrand.objects.get_or_create(name=brand_name)
    truck_model, _ = TruckModel.objects.get_or_create(brand=brand, name=model_name)
    return truck_model


def make_truck(**kw):
    defaults = dict(
        license_plate='ABC1D23', truck_model=make_truck_model(),
        color='branca', chassis='12345678901234567', year=2020,
    )
    defaults.update(kw)
    return Truck.objects.create(**defaults)


@pytest.mark.django_db
class TestTruckListLivePoll:
    def test_since_returns_only_newer_trucks(self):
        user = make_user()
        now = timezone.now()
        older = make_truck(license_plate='AAA1A11', chassis='11111111111111111')
        Truck.objects.filter(pk=older.pk).update(created_at=now - timedelta(minutes=10))
        newer = make_truck(license_plate='BBB2B22', chassis='22222222222222222')
        Truck.objects.filter(pk=newer.pk).update(created_at=now)

        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('trucks:list'),
            {'since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert 'BBB2B22' in body['html']
        assert 'AAA1A11' not in body['html']

    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('trucks:list'), {'since': timezone.now().isoformat()})
        assert response.status_code == 302

    def test_renders_with_zero_trucks(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('trucks:list'))

        assert response.status_code == 200
        assert b'infinite-tbody' in response.content
        assert b'startLivePoll' in response.content


def make_edit_user():
    from accounts.models import UserProfile
    user = User.objects.create_user(username='editor', password='pass')
    user.profile.role = UserProfile.MASTER
    user.profile.save()
    return user


def make_driver(**kw):
    from datetime import date

    from employees.models import Employee
    defaults = dict(name='Driver Person', role='Motorista', hire_date=date(2020, 1, 1), is_driver=True)
    defaults.update(kw)
    return Employee.objects.create(**defaults)


@pytest.mark.django_db
class TestTruckListLiveUpdate:
    def test_driver_assignment_bumps_updated_at_and_is_picked_up(self):
        user = make_edit_user()
        truck = make_truck()
        now = timezone.now()
        Truck.objects.filter(pk=truck.pk).update(updated_at=now - timedelta(minutes=10))
        driver = make_driver()

        client = Client()
        client.force_login(user)

        assign_resp = client.post(reverse('trucks:assign', kwargs={'pk': truck.pk}), {'driver': driver.pk, 'notes': ''})
        assert assign_resp.status_code == 302

        response = client.get(
            reverse('trucks:list'),
            {'changed_since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert truck.license_plate in body['html']
        assert driver.name in body['html']
        assert body['removed_ids'] == []

    def test_driver_unassignment_is_picked_up(self):
        from trucks.models import TruckAssignment

        user = make_edit_user()
        truck = make_truck()
        driver = make_driver()
        TruckAssignment.objects.create(truck=truck, driver=driver)

        now = timezone.now()
        Truck.objects.filter(pk=truck.pk).update(updated_at=now - timedelta(minutes=10))

        client = Client()
        client.force_login(user)

        unassign_resp = client.post(reverse('trucks:unassign', kwargs={'pk': truck.pk}))
        assert unassign_resp.status_code == 302

        response = client.get(
            reverse('trucks:list'),
            {'changed_since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        body = response.json()
        assert body['count'] == 1
        assert truck.license_plate in body['html']

    def test_page_renders_with_startliveupdate(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('trucks:list'))

        assert response.status_code == 200
        assert b'startLiveUpdate' in response.content
