"""
Device-token auth mixin for kiosk-facing JSON endpoints (biometric/api_views.py).

Kiosk calls are machine-to-machine over the internet — no Django session/
cookie is ever involved — so auth here is a per-device bearer token, not
LoginRequiredMixin.

Includes an in-memory per-IP throttle for repeated auth failures, mirroring
the single-process design of employee_truck_control/rate_limit.py (this
project is single-process deployable, e.g. PythonAnywhere).
"""
from __future__ import annotations

import threading
import time

from django.http import JsonResponse
from django.views import View

from biometric.models import KioskDevice

_failures: dict[str, dict] = {}
_lock = threading.Lock()

MAX_FAILURES = 10
WINDOW_SECONDS = 600
BLOCK_SECONDS = 600


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


class DeviceTokenAuthMixin(View):
    """
    Verifies an ``Authorization: Bearer <token>`` header against KioskDevice
    on every request. Sets ``self.device`` on success; returns 401 JSON
    otherwise. Views using this mixin for POST/PUT/DELETE must also be
    decorated with ``@method_decorator(csrf_exempt, name='dispatch')`` —
    these calls never carry a Django session/CSRF cookie, so CSRF protection
    (which guards against ambient cookie credentials in a browser) doesn't
    apply here.
    """

    def dispatch(self, request, *args, **kwargs):
        ip = _client_ip(request)
        now = time.monotonic()

        with _lock:
            entry = _failures.get(ip)
            if entry and entry.get('blocked_until', 0) > now:
                remaining = int(entry['blocked_until'] - now)
                return JsonResponse(
                    {
                        'error': 'too_many_attempts',
                        'detail': f'Tente novamente em {remaining} segundos.',
                    },
                    status=429,
                )

        auth_header = request.headers.get('Authorization', '')
        raw_token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else ''
        device = KioskDevice.authenticate(raw_token, ip=ip) if raw_token else None

        if device is None:
            self._record_failure(ip)
            return JsonResponse(
                {'error': 'unauthorized', 'detail': 'Token de dispositivo ausente ou inválido.'},
                status=401,
            )

        with _lock:
            _failures.pop(ip, None)

        self.device = device
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _record_failure(ip: str) -> None:
        now = time.monotonic()
        with _lock:
            entry = _failures.get(ip)
            if entry is None or now - entry.get('window_start', 0) > WINDOW_SECONDS:
                _failures[ip] = {'count': 1, 'window_start': now}
            else:
                entry['count'] += 1
                if entry['count'] >= MAX_FAILURES:
                    entry['blocked_until'] = now + BLOCK_SECONDS
