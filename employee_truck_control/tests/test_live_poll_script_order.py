import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


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
    """

    def test_definition_precedes_every_call_site(self):
        user = User.objects.create_user(username='plain', password='pass')
        client = Client()
        client.force_login(user)

        response = client.get(reverse('employees:list'))
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
                f'startLivePoll is called at index {call_index} but defined at '
                f'index {definition_index} — the call happens first in document '
                f'order, so it would fail silently in a real browser.'
            )
            call_index += 1

        assert found_any_call, 'no startLivePoll(...) call found on the employees list page'
