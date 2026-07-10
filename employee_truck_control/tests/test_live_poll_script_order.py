import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


def make_master_user():
    return User.objects.create_user(username='boss', password='pass', is_superuser=True)


@pytest.mark.django_db
class TestLivePollScriptOrder:
    """
    Regression test for a real bug: window.startLivePoll was defined near
    the end of base.html, AFTER {% block content %} — but child templates
    call it from an inline <script> placed inside that content block.
    Browsers execute inline scripts in document order, so the call site
    always ran before the definition existed, meaning live-poll never
    actually started in any real browser (silent no-op, no console error
    visible without dev tools open) despite every server-side test passing.

    Covers every page that calls window.startLivePoll(...), so any future
    page added to this list gets the same safety check for free.
    """

    URL_NAMES = [
        'employees:list',
        'accounts:system_logs',
        'accounts:manage_users',
        'visitors:list',
        'trucks:list',
    ]

    @pytest.mark.parametrize('url_name', URL_NAMES)
    def test_definition_precedes_every_call_site(self, url_name):
        user = make_master_user()  # master covers every page, incl. master-only ones
        client = Client()
        client.force_login(user)

        response = client.get(reverse(url_name))
        assert response.status_code == 200
        content = response.content.decode()

        definition_index = content.find('window.startLivePoll = function')
        assert definition_index != -1, 'window.startLivePoll definition not found on the page'

        call_index = 0
        found_any_call = False
        while True:
            call_index = content.find('startLivePoll({', call_index)
            if call_index == -1:
                break
            found_any_call = True
            assert definition_index < call_index, (
                f'[{url_name}] startLivePoll is called at index {call_index} but '
                f'defined at index {definition_index} — the call happens first in '
                f'document order, so it would fail silently in a real browser.'
            )
            call_index += 1

        assert found_any_call, f'no startLivePoll(...) call found on {url_name}'
