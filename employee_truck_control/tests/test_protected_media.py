import os

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse


def make_user():
    return User.objects.create_user(username='plain', password='pass')


@pytest.fixture
def media_file(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    sub = tmp_path / 'employees' / 'photos'
    sub.mkdir(parents=True)
    file_path = sub / 'someone.jpg'
    file_path.write_bytes(b'fake-jpeg-bytes')
    return 'employees/photos/someone.jpg'


@pytest.mark.django_db
class TestProtectedMediaView:
    def test_requires_login(self, media_file):
        client = Client()
        response = client.get(f'/media/{media_file}')
        assert response.status_code == 302
        assert '/accounts/login/' in response['Location']

    def test_authenticated_user_gets_the_file_in_debug_mode(self, media_file, settings):
        settings.DEBUG = True
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(f'/media/{media_file}')

        assert response.status_code == 200
        assert b''.join(response.streaming_content) == b'fake-jpeg-bytes'

    def test_missing_file_is_404_in_debug_mode(self, settings, tmp_path):
        settings.DEBUG = True
        settings.MEDIA_ROOT = str(tmp_path)
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get('/media/employees/photos/does-not-exist.jpg')

        assert response.status_code == 404

    def test_production_mode_hands_off_to_nginx_via_x_accel_redirect(self, media_file, settings):
        settings.DEBUG = False
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(f'/media/{media_file}')

        assert response.status_code == 200
        assert response['X-Accel-Redirect'] == f'/protected-media/{media_file}'

    def test_path_traversal_is_blocked(self, settings, tmp_path):
        settings.DEBUG = True
        settings.MEDIA_ROOT = str(tmp_path)
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get('/media/../../employee_truck_control/settings.py')

        assert response.status_code == 404
