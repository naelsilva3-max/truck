"""
Unit tests for the "Relatórios" hub view (employee_truck_control/views.py).
"""
import pytest
from django.contrib.auth.models import User
from django.urls import reverse


@pytest.fixture
def logged_in_client(client):
    user = User.objects.create_user(username="reportuser", password="pass")
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestReportsIndexView:
    def test_requires_login(self, client):
        response = client.get(reverse('reports_index'))
        assert response.status_code == 302

    def test_lists_employee_report(self, logged_in_client):
        response = logged_in_client.get(reverse('reports_index'))
        assert response.status_code == 200
        assert 'Relatório de Funcionários' in response.content.decode()
        assert reverse('employees:report_pdf') in response.content.decode()

    def test_lists_truck_report(self, logged_in_client):
        response = logged_in_client.get(reverse('reports_index'))
        assert response.status_code == 200
        assert 'Relatório de Caminhões' in response.content.decode()
        assert reverse('trucks:report_pdf') in response.content.decode()
