"""
LoginRateLimitMiddleware

Blocks brute-force login attempts by tracking failed POSTs to the login URL,
both per IP address and per submitted account (username/CPF field). After
MAX_ATTEMPTS failures within WINDOW_SECONDS the IP is blocked for
BLOCK_SECONDS; independently, after MAX_ATTEMPTS_ACCOUNT failures against the
same submitted username/CPF within WINDOW_SECONDS_ACCOUNT it's blocked for
BLOCK_SECONDS_ACCOUNT. The per-IP limit alone doesn't stop a distributed
attacker (many IPs) targeting a single account, hence the second dimension.

Uses an in-memory store — sufficient for single-process deployments.
For multi-process/multi-server deployments, replace the stores with a Redis backend.
"""
from __future__ import annotations

import threading
import time

from django.conf import settings
from django.http import HttpResponse

_store: dict[str, dict] = {}
_account_store: dict[str, dict] = {}
_lock = threading.Lock()

MAX_ATTEMPTS: int = getattr(settings, 'LOGIN_RATE_LIMIT_ATTEMPTS', 10)
WINDOW_SECONDS: int = getattr(settings, 'LOGIN_RATE_LIMIT_WINDOW', 600)   # 10 min
BLOCK_SECONDS: int = getattr(settings, 'LOGIN_RATE_LIMIT_BLOCK', 600)     # 10 min

# Looser than the per-IP limit: a legitimate user could trigger this from one
# IP by mistyping their password, so we allow more attempts before blocking,
# but still cap it to stop a distributed (multi-IP) attack on one account.
MAX_ATTEMPTS_ACCOUNT: int = getattr(settings, 'LOGIN_RATE_LIMIT_ACCOUNT_ATTEMPTS', 15)
WINDOW_SECONDS_ACCOUNT: int = getattr(settings, 'LOGIN_RATE_LIMIT_ACCOUNT_WINDOW', 900)   # 15 min
BLOCK_SECONDS_ACCOUNT: int = getattr(settings, 'LOGIN_RATE_LIMIT_ACCOUNT_BLOCK', 900)     # 15 min

LOGIN_PATH: str = settings.LOGIN_URL


def _get_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _get_account_key(request) -> str:
    return request.POST.get('username', '').strip().lower()


class LoginRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path == LOGIN_PATH:
            ip = _get_ip(request)
            account = _get_account_key(request)
            now = time.monotonic()

            with _lock:
                ip_entry = _store.get(ip)
                account_entry = _account_store.get(account) if account else None

                # Check if currently blocked, either dimension
                blocked_entry = None
                if ip_entry and ip_entry.get('blocked_until', 0) > now:
                    blocked_entry = ip_entry
                elif account_entry and account_entry.get('blocked_until', 0) > now:
                    blocked_entry = account_entry

                if blocked_entry is not None:
                    remaining = int(blocked_entry['blocked_until'] - now)
                    return HttpResponse(
                        f'Muitas tentativas de login. Tente novamente em {remaining} segundos.',
                        status=429,
                        content_type='text/plain; charset=utf-8',
                    )

                response = self.get_response(request)

                # On failed login (Django redirects back to login on failure)
                if response.status_code in (200, 302) and not request.user.is_authenticated:
                    if ip_entry is None or now - ip_entry.get('window_start', 0) > WINDOW_SECONDS:
                        _store[ip] = {'count': 1, 'window_start': now}
                    else:
                        ip_entry['count'] += 1
                        if ip_entry['count'] >= MAX_ATTEMPTS:
                            ip_entry['blocked_until'] = now + BLOCK_SECONDS

                    if account:
                        if account_entry is None or now - account_entry.get('window_start', 0) > WINDOW_SECONDS_ACCOUNT:
                            _account_store[account] = {'count': 1, 'window_start': now}
                        else:
                            account_entry['count'] += 1
                            if account_entry['count'] >= MAX_ATTEMPTS_ACCOUNT:
                                account_entry['blocked_until'] = now + BLOCK_SECONDS_ACCOUNT
                else:
                    # Successful login — clear both counters
                    _store.pop(ip, None)
                    if account:
                        _account_store.pop(account, None)

                return response

        return self.get_response(request)
