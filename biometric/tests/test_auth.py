"""
Unit tests for biometric.auth.DeviceTokenAuthMixin.
"""
import pytest
from django.http import JsonResponse
from django.test import RequestFactory

from biometric import auth as auth_module
from biometric.auth import DeviceTokenAuthMixin
from biometric.models import KioskDevice


class _DummyView(DeviceTokenAuthMixin):
    """Minimal view exercising the mixin; echoes back the authenticated device's name."""

    def get(self, request):
        return JsonResponse({'device_name': self.device.name})


@pytest.fixture(autouse=True)
def _reset_throttle():
    auth_module._failures.clear()
    yield
    auth_module._failures.clear()


@pytest.mark.django_db
class TestDeviceTokenAuthMixin:
    def _request(self, token: str | None = None):
        rf = RequestFactory()
        headers = {}
        if token is not None:
            headers['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        return rf.get('/whatever/', **headers)

    def test_missing_header_returns_401(self):
        request = self._request(token=None)
        response = _DummyView.as_view()(request)
        assert response.status_code == 401

    def test_invalid_token_returns_401(self):
        request = self._request(token='not-a-real-token')
        response = _DummyView.as_view()(request)
        assert response.status_code == 401

    def test_valid_token_passes_through_and_sets_device(self):
        device, raw_token = KioskDevice.issue(name='Quiosque Teste')
        request = self._request(token=raw_token)
        response = _DummyView.as_view()(request)
        assert response.status_code == 200
        import json
        assert json.loads(response.content)['device_name'] == 'Quiosque Teste'

    def test_revoked_device_token_returns_401(self):
        device, raw_token = KioskDevice.issue(name='Quiosque Teste')
        device.is_active = False
        device.save(update_fields=['is_active'])
        request = self._request(token=raw_token)
        response = _DummyView.as_view()(request)
        assert response.status_code == 401

    def test_throttle_blocks_after_max_failures(self):
        rf = RequestFactory()
        for _ in range(auth_module.MAX_FAILURES):
            request = rf.get('/whatever/', REMOTE_ADDR='9.9.9.9')
            _DummyView.as_view()(request)

        request = rf.get('/whatever/', REMOTE_ADDR='9.9.9.9')
        response = _DummyView.as_view()(request)
        assert response.status_code == 429

    def test_throttle_is_per_ip(self):
        rf = RequestFactory()
        for _ in range(auth_module.MAX_FAILURES):
            request = rf.get('/whatever/', REMOTE_ADDR='1.1.1.1')
            _DummyView.as_view()(request)

        # A different IP must not be affected by 1.1.1.1's lockout.
        device, raw_token = KioskDevice.issue(name='Outro Quiosque')
        request = rf.get('/whatever/', REMOTE_ADDR='2.2.2.2', HTTP_AUTHORIZATION=f'Bearer {raw_token}')
        response = _DummyView.as_view()(request)
        assert response.status_code == 200
