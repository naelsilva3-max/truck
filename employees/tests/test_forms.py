import io
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from employees.forms import EmployeeForm


def _make_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='white').save(buffer, format='JPEG')
    return buffer.getvalue()


def _make_pdf_bytes() -> bytes:
    return b'%PDF-1.4\n%%EOF'


def _valid_form_data(**overrides):
    data = {'name': 'Employee Teste', 'role': 'Operador', 'hire_date': date(2020, 1, 1)}
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestEmployeeFormDocumentPhoto:
    def test_accepts_pdf_document_photo(self):
        pdf = SimpleUploadedFile('rg.pdf', _make_pdf_bytes(), content_type='application/pdf')
        form = EmployeeForm(data=_valid_form_data(), files={'document_photo': pdf})

        form.is_valid()
        assert 'document_photo' not in form.errors

    def test_accepts_image_document_photo(self):
        image = SimpleUploadedFile('rg.jpg', _make_jpeg_bytes(), content_type='image/jpeg')
        form = EmployeeForm(data=_valid_form_data(), files={'document_photo': image})

        form.is_valid()
        assert 'document_photo' not in form.errors

    def test_rejects_garbage_document_photo(self):
        fake = SimpleUploadedFile('rg.pdf', b'not a real pdf or image', content_type='application/pdf')
        form = EmployeeForm(data=_valid_form_data(), files={'document_photo': fake})

        assert not form.is_valid()
        assert 'document_photo' in form.errors

    def test_photo_field_still_rejects_pdf(self):
        """The face-photo field (`photo`) is image-only -- PDFs must not be
        accepted there, only for document_photo."""
        pdf = SimpleUploadedFile('face.pdf', _make_pdf_bytes(), content_type='application/pdf')
        form = EmployeeForm(data=_valid_form_data(), files={'photo': pdf})

        assert not form.is_valid()
        assert 'photo' in form.errors
