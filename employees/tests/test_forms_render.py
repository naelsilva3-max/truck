from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from accounts.models import UserProfile
from employees.models import Employee


def make_admin_user():
    user = User.objects.create_user(username='boss', password='pass')
    user.profile.role = UserProfile.MASTER
    user.profile.save()
    return user


@pytest.mark.django_db
class TestEmployeeFormRendersWithDocumentVariants:
    def test_create_form_renders(self):
        user = make_admin_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('employees:create'))

        assert response.status_code == 200
        assert b'camera-pdf-preview' in response.content
        assert b'camera-pdf-embed' in response.content

    def test_edit_form_renders_with_existing_pdf_document(self):
        user = make_admin_user()
        emp = Employee.objects.create(name='Doc Holder', role='Op', hire_date=date(2020, 1, 1))
        emp.document_photo.save('rg.pdf', SimpleUploadedFile('rg.pdf', b'%PDF-1.4\n%%EOF'), save=True)

        client = Client()
        client.force_login(user)

        response = client.get(reverse('employees:update', kwargs={'pk': emp.pk}))

        assert response.status_code == 200
        assert b'pdf-thumb-link' in response.content
        assert b'Abrir PDF atual' in response.content

    def test_edit_form_renders_with_existing_image_document(self):
        import io

        from PIL import Image

        user = make_admin_user()
        emp = Employee.objects.create(name='Doc Holder 2', role='Op', hire_date=date(2020, 1, 1))
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2), color='white').save(buffer, format='JPEG')
        emp.document_photo.save('rg.jpg', SimpleUploadedFile('rg.jpg', buffer.getvalue()), save=True)

        client = Client()
        client.force_login(user)

        response = client.get(reverse('employees:update', kwargs={'pk': emp.pk}))

        assert response.status_code == 200
        assert b'pdf-thumb-link' not in response.content
        content = response.content.decode()
        assert 'Documento atual' in content
