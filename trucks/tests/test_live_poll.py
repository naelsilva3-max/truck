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
