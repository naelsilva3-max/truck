import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestContentSecurityPolicyHeader:
    def test_csp_header_present_on_every_response(self):
        client = Client()
        response = client.get(reverse('login'))

        assert 'Content-Security-Policy' in response.headers
        csp = response.headers['Content-Security-Policy']
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp
