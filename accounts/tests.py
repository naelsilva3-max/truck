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
