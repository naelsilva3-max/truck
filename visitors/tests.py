import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from visitors.forms import VisitorForm


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
