from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from employees.models import Employee


def make_master_user():
    return User.objects.create_user(username='boss', password='pass', is_superuser=True)


def make_employee():
    return Employee.objects.create(name='Script Order Test', role='Op', hire_date=date(2020, 1, 1))


@pytest.mark.django_db
class TestLiveScriptOrder:
    """
    Regression test for a real bug: window.startLivePoll was defined near
    the end of base.html, AFTER {% block content %} — but child templates
    call it from an inline <script> placed inside that content block.
    Browsers execute inline scripts in document order, so the call site
    always ran before the definition existed, meaning live-poll never
    actually started in any real browser (silent no-op, no console error
    visible without dev tools open) despite every server-side test passing.

    Covers every page that calls window.startLivePoll(...) and/or
    window.startLiveUpdate(...), so any future page added to either list
    gets the same safety check for free.
    """

    # (url_name, kwargs) for pages using startLivePoll (new-row insertion)
    POLL_PAGES = [
        ('employees:list', {}),
        ('accounts:system_logs', {}),
        ('accounts:manage_users', {}),
        ('visitors:list', {}),
        ('trucks:list', {}),
    ]

    # (url_name, kwargs) for pages using startLiveUpdate (existing-row replace)
    UPDATE_PAGES = [
        ('employees:list', {}),
        ('accounts:manage_users', {}),
        ('trucks:list', {}),
    ]

    def _get_page(self, client, url_name, kwargs):
        if url_name == 'attendance:list':
            kwargs = {**kwargs, 'pk': make_employee().pk}
        return client.get(reverse(url_name, kwargs=kwargs))

    def _assert_definition_precedes_calls(self, content, fn_name, page_label):
        definition_index = content.find(f'window.{fn_name} = function')
        assert definition_index != -1, f'window.{fn_name} definition not found on {page_label}'

        call_index = 0
        found_any_call = False
        while True:
            call_index = content.find(f'{fn_name}({{', call_index)
            if call_index == -1:
                break
            found_any_call = True
            assert definition_index < call_index, (
                f'[{page_label}] {fn_name} is called at index {call_index} but '
                f'defined at index {definition_index} — the call happens first in '
                f'document order, so it would fail silently in a real browser.'
            )
            call_index += 1

        assert found_any_call, f'no {fn_name}(...) call found on {page_label}'

    @pytest.mark.parametrize('url_name,kwargs', POLL_PAGES)
    def test_startlivepoll_definition_precedes_every_call_site(self, url_name, kwargs):
        user = make_master_user()  # master covers every page, incl. master-only ones
        client = Client()
        client.force_login(user)

        response = self._get_page(client, url_name, kwargs)
        assert response.status_code == 200
        self._assert_definition_precedes_calls(response.content.decode(), 'startLivePoll', url_name)

    @pytest.mark.parametrize('url_name,kwargs', UPDATE_PAGES)
    def test_startliveupdate_definition_precedes_every_call_site(self, url_name, kwargs):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = self._get_page(client, url_name, kwargs)
        assert response.status_code == 200
        self._assert_definition_precedes_calls(response.content.decode(), 'startLiveUpdate', url_name)

    def test_attendance_list_page(self):
        user = make_master_user()
        client = Client()
        client.force_login(user)

        response = self._get_page(client, 'attendance:list', {})
        assert response.status_code == 200
        content = response.content.decode()
        self._assert_definition_precedes_calls(content, 'startLivePoll', 'attendance:list')
        self._assert_definition_precedes_calls(content, 'startLiveUpdate', 'attendance:list')
