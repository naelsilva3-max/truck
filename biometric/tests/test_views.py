"""
Unit tests for biometric.views.KioskTokenGenerateView -- the web equivalent
of `python manage.py kiosk_device create`.
"""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from biometric.models import KioskDevice


def make_master_user():
    return User.objects.create_user(username="master", password="pass", is_superuser=True)


def make_plain_user():
    return User.objects.create_user(username="plain", password="pass")


@pytest.mark.django_db
class TestKioskTokenGenerateView:
    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('biometric:kiosk_token'))
        assert response.status_code in (302, 403)

    def test_non_master_is_redirected(self):
        user = make_plain_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('biometric:kiosk_token'))
        assert response.status_code == 302

    def test_get_lists_existing_devices(self):
        user = make_master_user()
        KioskDevice.issue(name="Recepção")
        client = Client()
        client.force_login(user)

        response = client.get(reverse('biometric:kiosk_token'))

        assert response.status_code == 200
        assert list(response.context['devices'].values_list('name', flat=True)) == ['Recepção']
        assert response.context['raw_token'] is None

    def test_post_creates_device_and_returns_raw_token(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_token'), {'name': 'Novo Quiosque'})

        assert response.status_code == 200
        assert response.context['raw_token'] is not None
        assert response.context['new_device'].name == 'Novo Quiosque'
        device = KioskDevice.objects.get(name='Novo Quiosque')
        assert device.is_active is True
        # The raw token round-trips through KioskDevice.authenticate.
        assert KioskDevice.authenticate(response.context['raw_token']).pk == device.pk

    def test_post_blank_name_shows_error_without_creating_device(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_token'), {'name': '   '})

        assert response.status_code == 200
        assert response.context['raw_token'] is None
        assert KioskDevice.objects.count() == 0

    def test_get_never_reshows_a_previously_generated_token(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)
        client.post(reverse('biometric:kiosk_token'), {'name': 'Quiosque X'})

        response = client.get(reverse('biometric:kiosk_token'))

        assert response.context['raw_token'] is None
