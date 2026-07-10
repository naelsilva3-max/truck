import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


def make_user(**kwargs):
    defaults = {'username': 'plain', 'password': 'OldPass123!', 'email': 'old@example.com'}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


@pytest.mark.django_db
class TestMyAccountView:
    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('accounts:my_account'))
        assert response.status_code == 302

    def test_get_shows_forms(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('accounts:my_account'))

        assert response.status_code == 200
        assert 'email_form' in response.context
        assert 'password_form' in response.context

    def test_update_email(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('accounts:my_account'), {
            'update_email': '1',
            'email': 'new@example.com',
        })

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.email == 'new@example.com'

    def test_update_email_rejects_duplicate(self):
        make_user(username='other', email='taken@example.com')
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('accounts:my_account'), {
            'update_email': '1',
            'email': 'taken@example.com',
        })

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email == 'old@example.com'

    def test_change_password(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('accounts:my_account'), {
            'change_password': '1',
            'old_password': 'OldPass123!',
            'new_password1': 'NewPass456!',
            'new_password2': 'NewPass456!',
        })

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.check_password('NewPass456!')

    def test_change_password_rejects_wrong_old_password(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.post(reverse('accounts:my_account'), {
            'change_password': '1',
            'old_password': 'wrong',
            'new_password1': 'NewPass456!',
            'new_password2': 'NewPass456!',
        })

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password('OldPass123!')


def make_master_user(**kwargs):
    defaults = {'username': 'boss', 'password': 'pass', 'is_superuser': True}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


@pytest.mark.django_db
class TestSystemLogLivePoll:
    def test_since_returns_only_newer_logs(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import SystemLog

        user = make_master_user()
        client = Client()
        client.force_login(user)
        SystemLog.objects.all().delete()  # force_login() itself creates a "login" SystemLog entry -- clear the slate

        now = timezone.now()
        older = SystemLog.objects.create(username='someone', action=SystemLog.ACTION_CREATE, description='old')
        SystemLog.objects.filter(pk=older.pk).update(timestamp=now - timedelta(minutes=10))
        newer = SystemLog.objects.create(username='someone', action=SystemLog.ACTION_UPDATE, description='new event')

        response = client.get(
            reverse('accounts:system_logs'),
            {'since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert 'new event' in body['html']
        assert 'old' not in body['html']

    def test_requires_master_role(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('accounts:system_logs'), {'since': '2026-01-01T00:00:00+00:00'})
        assert response.status_code == 302

    def test_page_renders_with_startlivepoll(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('accounts:system_logs'))

        assert response.status_code == 200
        assert b'startLivePoll' in response.content


@pytest.mark.django_db
class TestUserManageLivePoll:
    def test_since_returns_only_newer_users(self):
        from datetime import timedelta

        from django.utils import timezone

        master = make_master_user()
        client = Client()
        client.force_login(master)

        now = timezone.now()
        User.objects.filter(pk=master.pk).update(date_joined=now - timedelta(minutes=10))
        older = make_user(username='older_user', email='older@example.com')
        User.objects.filter(pk=older.pk).update(date_joined=now - timedelta(minutes=10))
        newer = make_user(username='newer_user', email='newer@example.com')
        User.objects.filter(pk=newer.pk).update(date_joined=now)

        response = client.get(
            reverse('accounts:manage_users'),
            {'since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert 'newer_user' in body['html']
        assert 'older_user' not in body['html']

    def test_requires_master_role(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        from django.utils import timezone
        response = client.get(reverse('accounts:manage_users'), {'since': timezone.now().isoformat()})
        assert response.status_code == 302

    def test_page_renders_with_startlivepoll(self):
        master = make_master_user()
        client = Client()
        client.force_login(master)

        response = client.get(reverse('accounts:manage_users'))

        assert response.status_code == 200
        assert b'startLivePoll' in response.content
