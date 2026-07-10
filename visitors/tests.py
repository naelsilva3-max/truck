import io
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from visitors.forms import VisitorForm
from visitors.models import Visit, Visitor


def _make_valid_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='white').save(buffer, format='JPEG')
    return buffer.getvalue()


def _valid_form_data(**overrides):
    data = {
        'name': 'Visitante Teste',
        'phone': '11999999999',
        'rg': '12.345.678-9',
        'cpf': '390.533.447-05',
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestVisitorFormPhotoValidation:
    def test_rejects_non_image_photo(self):
        fake_photo = SimpleUploadedFile('malicious.jpg', b'not-an-image-at-all', content_type='image/jpeg')
        form = VisitorForm(data=_valid_form_data(), files={'photo': fake_photo})

        assert not form.is_valid()
        assert 'photo' in form.errors

    def test_rejects_non_image_document_photo(self):
        fake_doc = SimpleUploadedFile('malicious.jpg', b'not-an-image-at-all', content_type='image/jpeg')
        form = VisitorForm(data=_valid_form_data(), files={'document_photo': fake_doc})

        assert not form.is_valid()
        assert 'document_photo' in form.errors

    def test_accepts_valid_image_photo(self):
        photo = SimpleUploadedFile('face.jpg', _make_valid_jpeg_bytes(), content_type='image/jpeg')
        form = VisitorForm(data=_valid_form_data(), files={'photo': photo})

        form.is_valid()
        assert 'photo' not in form.errors

    def test_accepts_pdf_document_photo(self):
        pdf = SimpleUploadedFile('rg.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')
        form = VisitorForm(data=_valid_form_data(), files={'document_photo': pdf})

        form.is_valid()
        assert 'document_photo' not in form.errors

    def test_photo_field_still_rejects_pdf(self):
        pdf = SimpleUploadedFile('face.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')
        form = VisitorForm(data=_valid_form_data(), files={'photo': pdf})

        assert not form.is_valid()
        assert 'photo' in form.errors


@pytest.mark.django_db
class TestVisitorFormRendersWithDocumentVariants:
    def test_create_form_renders(self):
        user = User.objects.create_user(username='someone', password='pass')
        client = Client()
        client.force_login(user)

        response = client.get(reverse('visitors:create'))

        assert response.status_code == 200
        assert b'camera-pdf-preview' in response.content
        assert b'camera-btn-file' in response.content  # was missing before this change

    def test_edit_form_renders_with_existing_pdf_document(self):
        user = User.objects.create_user(username='someone2', password='pass')
        visitor = Visitor.objects.create(name='Doc Visitor')
        visitor.document_photo.save('rg.pdf', SimpleUploadedFile('rg.pdf', b'%PDF-1.4\n%%EOF'), save=True)

        client = Client()
        client.force_login(user)

        response = client.get(reverse('visitors:update', kwargs={'pk': visitor.pk}))

        assert response.status_code == 200
        assert b'pdf-thumb-link' in response.content


def make_user():
    return User.objects.create_user(username='plain', password='pass')


def make_visitor(**kw):
    defaults = dict(name='Test Visitor')
    defaults.update(kw)
    return Visitor.objects.create(**defaults)


@pytest.mark.django_db
class TestVisitorListLivePoll:
    def test_since_returns_only_newer_visitors(self):
        user = make_user()
        now = timezone.now()
        older = make_visitor(name='Older Visitor')
        Visitor.objects.filter(pk=older.pk).update(created_at=now - timedelta(minutes=10))
        newer = make_visitor(name='Newer Visitor')
        Visitor.objects.filter(pk=newer.pk).update(created_at=now)

        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('visitors:list'),
            {'since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert 'Newer Visitor' in body['html']
        assert 'Older Visitor' not in body['html']

    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('visitors:list'), {'since': timezone.now().isoformat()})
        assert response.status_code == 302

    def test_renders_with_zero_visitors(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('visitors:list'))

        assert response.status_code == 200
        assert b'infinite-tbody' in response.content
        assert b'startLivePoll' in response.content


def make_responsible_employee(**kw):
    from datetime import date

    from employees.models import Employee
    defaults = dict(name='Responsible Person', role='Recepção', hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)


def make_visit(**kw):
    from datetime import time

    defaults = dict(
        visitor=make_visitor(name=f'Visitor {Visitor.objects.count() + 1}'),
        visit_date=timezone.localdate(),
        arrival_time=time(9, 0),
        scheduled_departure_time=time(17, 0),
        responsible=make_responsible_employee(),
    )
    defaults.update(kw)
    return Visit.objects.create(**defaults)


@pytest.mark.django_db
class TestVisitListLivePoll:
    def test_since_returns_only_newer_visits_in_active_tab(self):
        user = make_user()
        now = timezone.now()
        older = make_visit()
        Visit.objects.filter(pk=older.pk).update(created_at=now - timedelta(minutes=10))
        newer = make_visit()
        Visit.objects.filter(pk=newer.pk).update(created_at=now)

        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('visitors:visit_list'),
            {'filter': 'active', 'since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 1
        assert newer.visitor.name in body['html']
        assert older.visitor.name not in body['html']

    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('visitors:visit_list'), {'since': timezone.now().isoformat()})
        assert response.status_code == 302

    def test_renders_with_zero_visits(self):
        user = make_user()
        client = Client()
        client.force_login(user)

        response = client.get(reverse('visitors:visit_list'))

        assert response.status_code == 200
        assert b'infinite-tbody' in response.content
        assert b'startLivePoll' in response.content
        assert b'startLiveUpdate' in response.content


@pytest.mark.django_db
class TestVisitListLiveUpdate:
    def test_departure_removes_visit_from_active_tab(self):
        user = make_user()
        visit = make_visit()
        now = timezone.now()
        Visit.objects.filter(pk=visit.pk).update(updated_at=now - timedelta(minutes=10))

        client = Client()
        client.force_login(user)

        depart_resp = client.post(reverse('visitors:visit_depart', kwargs={'pk': visit.pk}))
        assert depart_resp.status_code == 302

        response = client.get(
            reverse('visitors:visit_list'),
            {'filter': 'active', 'changed_since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        assert response.status_code == 200
        body = response.json()
        assert body['count'] == 0
        assert body['removed_ids'] == [visit.pk]

    def test_departure_adds_visit_to_completed_tab(self):
        user = make_user()
        visit = make_visit()
        now = timezone.now()
        Visit.objects.filter(pk=visit.pk).update(updated_at=now - timedelta(minutes=10))

        client = Client()
        client.force_login(user)

        client.post(reverse('visitors:visit_depart', kwargs={'pk': visit.pk}))

        response = client.get(
            reverse('visitors:visit_list'),
            {'filter': 'completed', 'changed_since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        body = response.json()
        assert body['count'] == 1
        assert body['removed_ids'] == []
        assert visit.visitor.name in body['html']

    def test_departure_visible_in_all_tab(self):
        user = make_user()
        visit = make_visit()
        now = timezone.now()
        Visit.objects.filter(pk=visit.pk).update(updated_at=now - timedelta(minutes=10))

        client = Client()
        client.force_login(user)

        client.post(reverse('visitors:visit_depart', kwargs={'pk': visit.pk}))

        response = client.get(
            reverse('visitors:visit_list'),
            {'filter': 'all', 'changed_since': (now - timedelta(minutes=1)).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        body = response.json()
        assert body['count'] == 1
        assert body['removed_ids'] == []
