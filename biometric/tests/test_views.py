"""
Unit tests for biometric.views.KioskTokenGenerateView -- the web equivalent
of `python manage.py kiosk_device create`.
"""
import os

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from biometric.models import KioskDevice, KioskInstallerBuild


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


def _make_exe(name='ZK9500KioskSetup-1.1.exe', content=b'MZ-fake-exe-bytes'):
    return SimpleUploadedFile(name, content, content_type='application/octet-stream')


@pytest.mark.django_db
class TestKioskInstallerListView:
    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('biometric:kiosk_installer'))
        assert response.status_code in (302, 403)

    def test_non_master_is_redirected(self):
        user = make_plain_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('biometric:kiosk_installer'))
        assert response.status_code == 302

    def test_get_lists_existing_builds(self):
        user = make_master_user()
        KioskInstallerBuild.objects.create(version='1.0', file=_make_exe('ZK9500KioskSetup-1.0.exe'))
        client = Client()
        client.force_login(user)

        response = client.get(reverse('biometric:kiosk_installer'))

        assert response.status_code == 200
        assert list(response.context['builds'].values_list('version', flat=True)) == ['1.0']

    def test_post_uploads_new_build(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_installer'), {
            'version': '1.1', 'notes': 'Ciclo de almoço', 'file': _make_exe(),
        })

        assert response.status_code == 302
        build = KioskInstallerBuild.objects.get(version='1.1')
        assert build.notes == 'Ciclo de almoço'
        assert build.uploaded_by == user
        assert build.file.name.endswith('.exe')

    def test_post_rejects_non_exe_file(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_installer'), {
            'version': '1.1',
            'file': SimpleUploadedFile('not-an-installer.txt', b'plain text'),
        }, follow=True)

        assert response.status_code == 200
        assert KioskInstallerBuild.objects.count() == 0

    def test_post_missing_version_shows_error_without_creating_build(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_installer'), {'version': '', 'file': _make_exe()})

        assert response.status_code == 302
        assert KioskInstallerBuild.objects.count() == 0

    def test_upload_over_size_limit_is_rejected(self, monkeypatch):
        from biometric.views import KioskInstallerListView
        monkeypatch.setattr(KioskInstallerListView, 'MAX_UPLOAD_BYTES', 5)  # smaller than _make_exe()'s content

        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_installer'), {'version': '9.9', 'file': _make_exe()})

        assert response.status_code == 302
        assert KioskInstallerBuild.objects.count() == 0


@pytest.mark.django_db
class TestKioskInstallerDownloadView:
    def test_requires_login(self):
        build = KioskInstallerBuild.objects.create(version='1.0', file=_make_exe())
        client = Client()
        response = client.get(reverse('biometric:kiosk_installer_download', kwargs={'pk': build.pk}))
        assert response.status_code in (302, 403)

    def test_non_master_is_redirected(self):
        build = KioskInstallerBuild.objects.create(version='1.0', file=_make_exe())
        user = make_plain_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('biometric:kiosk_installer_download', kwargs={'pk': build.pk}))
        assert response.status_code == 302

    @override_settings(DEBUG=True)
    def test_master_downloads_file_content_in_debug(self):
        content = b'MZ-fake-exe-bytes-for-download-test'
        build = KioskInstallerBuild.objects.create(version='1.0', file=_make_exe(content=content))
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('biometric:kiosk_installer_download', kwargs={'pk': build.pk}))

        assert response.status_code == 200
        assert b''.join(response.streaming_content) == content
        assert 'ZK9500KioskSetup-1.0.exe' in response['Content-Disposition']

    def test_production_uses_x_accel_redirect(self):
        build = KioskInstallerBuild.objects.create(version='1.0', file=_make_exe())
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('biometric:kiosk_installer_download', kwargs={'pk': build.pk}))

        assert response.status_code == 200
        assert response['X-Accel-Redirect'].startswith('/protected-media/kiosk_installer/')
        assert 'ZK9500KioskSetup-1.0.exe' in response['Content-Disposition']

    def test_unknown_build_404s(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)
        response = client.get(reverse('biometric:kiosk_installer_download', kwargs={'pk': 999999}))
        assert response.status_code == 404


@pytest.mark.django_db
class TestKioskInstallerDeleteView:
    def test_non_master_is_redirected(self):
        build = KioskInstallerBuild.objects.create(version='1.0', file=_make_exe())
        user = make_plain_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_installer_delete', kwargs={'pk': build.pk}))

        assert response.status_code == 302
        assert KioskInstallerBuild.objects.filter(pk=build.pk).exists()

    def test_master_deletes_build_and_file(self):
        build = KioskInstallerBuild.objects.create(version='1.0', file=_make_exe())
        file_path = build.file.path
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('biometric:kiosk_installer_delete', kwargs={'pk': build.pk}))

        assert response.status_code == 302
        assert not KioskInstallerBuild.objects.filter(pk=build.pk).exists()
        assert not os.path.exists(file_path)
