"""
Unit tests for biometric.models.KioskDevice and biometric.models.BiometricTemplate.
"""
from datetime import date

import pytest
from django.core.exceptions import ValidationError

from biometric.models import BiometricTemplate, KioskDevice
from employees.models import Employee


def make_employee(**kwargs) -> Employee:
    defaults = dict(name="João Silva", role="Operador", hire_date=date(2020, 1, 1))
    defaults.update(kwargs)
    return Employee.objects.create(**defaults)


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


@pytest.mark.django_db
class TestKioskDeviceIssue:
    def test_issue_creates_active_device(self):
        device, raw_token = KioskDevice.issue(name="Recepção - Teste")
        assert device.pk is not None
        assert device.is_active is True
        assert device.name == "Recepção - Teste"

    def test_issue_returns_high_entropy_token(self):
        _, raw_token = KioskDevice.issue(name="A")
        assert len(raw_token) >= 32

    def test_raw_token_is_never_persisted(self):
        device, raw_token = KioskDevice.issue(name="A")
        device.refresh_from_db()
        assert raw_token not in device.token_hash
        assert device.token_hash != raw_token

    def test_token_prefix_matches_start_of_raw_token(self):
        device, raw_token = KioskDevice.issue(name="A")
        assert raw_token.startswith(device.token_prefix)

    def test_two_issued_tokens_are_different(self):
        _, token1 = KioskDevice.issue(name="A")
        _, token2 = KioskDevice.issue(name="B")
        assert token1 != token2


@pytest.mark.django_db
class TestKioskDeviceAuthenticate:
    def test_authenticate_with_correct_token_returns_device(self):
        device, raw_token = KioskDevice.issue(name="Recepção")
        result = KioskDevice.authenticate(raw_token)
        assert result is not None
        assert result.pk == device.pk

    def test_authenticate_with_wrong_token_returns_none(self):
        KioskDevice.issue(name="Recepção")
        assert KioskDevice.authenticate("token-invalido-qualquer") is None

    def test_authenticate_with_empty_token_returns_none(self):
        assert KioskDevice.authenticate("") is None
        assert KioskDevice.authenticate(None) is None

    def test_authenticate_updates_last_seen(self):
        device, raw_token = KioskDevice.issue(name="Recepção")
        assert device.last_seen_at is None
        result = KioskDevice.authenticate(raw_token, ip="1.2.3.4")
        assert result.last_seen_at is not None
        assert result.last_seen_ip == "1.2.3.4"

    def test_authenticate_fails_for_revoked_device(self):
        device, raw_token = KioskDevice.issue(name="Recepção")
        device.is_active = False
        device.save(update_fields=['is_active'])
        assert KioskDevice.authenticate(raw_token) is None
