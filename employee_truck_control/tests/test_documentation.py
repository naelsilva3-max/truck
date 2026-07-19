"""
Unit tests for the in-app docs viewer (employee_truck_control/documentation.py
+ views), which renders docs/system/ and docs/manual/ as web pages.
"""
import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from employee_truck_control.documentation import SECTIONS, render_doc


@pytest.fixture
def logged_in_client(client):
    user = User.objects.create_user(username="docsuser", password="pass")
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestDocumentationIndexView:
    def test_requires_login(self, client):
        response = client.get(reverse('documentation_index'))
        assert response.status_code == 302

    def test_lists_every_known_section(self, logged_in_client):
        response = logged_in_client.get(reverse('documentation_index'))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Documentação técnica' in content
        assert 'Manual do usuário' in content


@pytest.mark.django_db
class TestDocumentationPageView:
    def test_requires_login(self, client):
        response = client.get(reverse('documentation_section', kwargs={'section': 'system'}))
        assert response.status_code == 302

    def test_unknown_section_is_404(self, logged_in_client):
        response = logged_in_client.get(
            reverse('documentation_page', kwargs={'section': 'nope', 'page': 'README'})
        )
        assert response.status_code == 404

    def test_unknown_page_is_404(self, logged_in_client):
        response = logged_in_client.get(
            reverse('documentation_page', kwargs={'section': 'system', 'page': 'nope'})
        )
        assert response.status_code == 404

    def test_path_traversal_attempt_is_404(self, logged_in_client):
        # The <str:page> URL converter already rejects any value containing
        # "/", so a same-segment traversal attempt is what's left to check --
        # the page allowlist in _file_path() must reject it too.
        response = logged_in_client.get(
            reverse('documentation_page', kwargs={'section': 'system', 'page': '..'})
        )
        assert response.status_code == 404

    @pytest.mark.parametrize('section', list(SECTIONS.keys()))
    def test_every_page_in_every_section_renders(self, logged_in_client, section):
        _, pages = SECTIONS[section]
        for page in pages:
            if page == 'README':
                url = reverse('documentation_section', kwargs={'section': section})
            else:
                url = reverse('documentation_page', kwargs={'section': section, 'page': page})
            response = logged_in_client.get(url)
            assert response.status_code == 200, f'{section}/{page} did not render'


class TestDocLinksResolve:
    """Guards against authoring mistakes: every relative .md link written
    inside our own docs must resolve to a known in-app page, so a reader
    never lands on a dead link."""

    @pytest.mark.parametrize('section', list(SECTIONS.keys()))
    def test_no_dangling_md_links_after_render(self, section):
        _, pages = SECTIONS[section]
        for page in pages:
            _, html = render_doc(section, page)
            dangling = re.findall(r'href="[^"]*\.md[^"]*"', html)
            assert not dangling, f'{section}/{page} has unresolved .md link(s): {dangling}'
