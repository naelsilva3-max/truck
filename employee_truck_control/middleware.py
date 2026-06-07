"""
BiometricTemplateProtectionMiddleware

Intercepts template context assignments to prevent BiometricTemplate objects
from being rendered directly in templates (Requirement 10.3 / LGPD).

Uses a thread-local flag + a monkey-patch on BaseContext.__setitem__ so that
any attempt to place a BiometricTemplate instance into a template context
during a request raises PermissionError immediately.
"""
from __future__ import annotations

import threading

_local = threading.local()


def _check_value(value) -> None:
    from employees.models import BiometricTemplate
    if isinstance(value, BiometricTemplate):
        raise PermissionError(
            "Direct access to BiometricTemplate objects in templates is forbidden. "
            "Expose only metadata (e.g. has_biometric, template size) instead."
        )
    if isinstance(value, (list, tuple)):
        for item in value:
            _check_value(item)


def _patch_base_context() -> None:
    from django.template.context import BaseContext

    if getattr(BaseContext, "_biometric_patched", False):
        return

    original_setitem = BaseContext.__setitem__

    def patched_setitem(self, key, value):
        if getattr(_local, "active", False):
            _check_value(value)
        return original_setitem(self, key, value)

    BaseContext.__setitem__ = patched_setitem
    BaseContext._biometric_patched = True


class BiometricTemplateProtectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        _patch_base_context()

    def __call__(self, request):
        _local.active = True
        try:
            response = self.get_response(request)
        finally:
            _local.active = False
        return response
