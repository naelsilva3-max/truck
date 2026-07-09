"""
LoginRateLimitMiddleware

Blocks brute-force login attempts by tracking failed POSTs to the login URL
per IP address. After MAX_ATTEMPTS failures within WINDOW_SECONDS the IP is
blocked for BLOCK_SECONDS.

Uses an in-memory store — sufficient for single-process deployments.
For multi-process/multi-server deployments, replace _store with a Redis backend.
"""
from __future__ import annotations

import threading
import time

from django.conf import settings
from django.http import HttpResponse

_store: dict[str, dict] = {}
_lock = threading.Lock()

MAX_ATTEMPTS: int = getattr(settings, 'LOGIN_RATE_LIMIT_ATTEMPTS', 10)
WINDOW_SECONDS: int = getattr(settings, 'LOGIN_RATE_LIMIT_WINDOW', 600)   # 10 min
BLOCK_SECONDS: int = getattr(settings, 'LOGIN_RATE_LIMIT_BLOCK', 600)     # 10 min
LOGIN_PATH: str = settings.LOGIN_URL


def _get_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


class LoginRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path == LOGIN_PATH:
            ip = _get_ip(request)
            now = time.monotonic()

            with _lock:
                entry = _store.get(ip)

                # Check if currently blocked
                if entry and entry.get('blocked_until', 0) > now:
                    remaining = int(entry['blocked_until'] - now)
                    return HttpResponse(
                        f'Muitas tentativas de login. Tente novamente em {remaining} segundos.',
                        status=429,
                        content_type='text/plain; charset=utf-8',
                    )

                response = self.get_response(request)

                # On failed login (Django redirects back to login on failure)
                if response.status_code in (200, 302) and not request.user.is_authenticated:
                    if entry is None or now - entry.get('window_start', 0) > WINDOW_SECONDS:
                        _store[ip] = {'count': 1, 'window_start': now}
                    else:
                        entry['count'] += 1
                        if entry['count'] >= MAX_ATTEMPTS:
                            entry['blocked_until'] = now + BLOCK_SECONDS
                else:
                    # Successful login — clear the counter
                    _store.pop(ip, None)

                return response

        return self.get_response(request)
