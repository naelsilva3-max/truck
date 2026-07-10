import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from employee_truck_control import rate_limit


@pytest.fixture(autouse=True)
def clear_rate_limit_stores():
    rate_limit._store.clear()
    rate_limit._account_store.clear()
    yield
    rate_limit._store.clear()
    rate_limit._account_store.clear()


@pytest.mark.django_db
class TestAccountRateLimit:
    def test_blocks_after_max_account_attempts_even_from_different_ips(self):
        User.objects.create_user(username='victim', password='correct-horse')
        client = Client()

        for i in range(rate_limit.MAX_ATTEMPTS_ACCOUNT):
            response = client.post(
                reverse('login'),
                {'username': 'victim', 'password': 'wrong', 'login_mode': 'username'},
                REMOTE_ADDR=f'10.0.0.{i % 250 + 1}',
            )
            assert response.status_code in (200, 302)

        blocked = client.post(
            reverse('login'),
            {'username': 'victim', 'password': 'wrong', 'login_mode': 'username'},
            REMOTE_ADDR='10.0.0.250',
        )
        assert blocked.status_code == 429

    def test_correct_login_clears_account_counter(self):
        User.objects.create_user(username='someone', password='correct-horse')
        client = Client()

        for _ in range(3):
            client.post(reverse('login'), {'username': 'someone', 'password': 'wrong', 'login_mode': 'username'})

        response = client.post(
            reverse('login'), {'username': 'someone', 'password': 'correct-horse', 'login_mode': 'username'}
        )
        assert response.status_code == 302
        assert 'someone' not in rate_limit._account_store

    def test_different_accounts_tracked_independently(self):
        User.objects.create_user(username='alice', password='pw')
        User.objects.create_user(username='bob', password='pw')
        client = Client()

        # Vary the IP so this only exercises the account-level counter, not
        # the (separate, already-tested) per-IP counter.
        for i in range(rate_limit.MAX_ATTEMPTS_ACCOUNT):
            client.post(
                reverse('login'),
                {'username': 'alice', 'password': 'wrong', 'login_mode': 'username'},
                REMOTE_ADDR=f'10.1.0.{i % 250 + 1}',
            )

        # bob's own attempt, from yet another fresh IP, should not be
        # blocked by alice's lockout.
        response = client.post(
            reverse('login'),
            {'username': 'bob', 'password': 'wrong', 'login_mode': 'username'},
            REMOTE_ADDR='10.2.0.1',
        )
        assert response.status_code != 429
