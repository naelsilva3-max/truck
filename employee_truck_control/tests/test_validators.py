import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from employee_truck_control.validators import validate_image_file, validate_image_or_pdf_file


def _make_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), color='white').save(buffer, format='JPEG')
    return buffer.getvalue()


def _make_pdf_bytes() -> bytes:
    # Minimal-but-real PDF: header + trailer is enough to pass the magic-byte check.
    return b'%PDF-1.4\n%%EOF'


class TestValidateImageOrPdfFile:
    def test_accepts_valid_image(self):
        f = SimpleUploadedFile('doc.jpg', _make_jpeg_bytes(), content_type='image/jpeg')
        validate_image_or_pdf_file(f)  # must not raise

    def test_accepts_valid_pdf(self):
        f = SimpleUploadedFile('doc.pdf', _make_pdf_bytes(), content_type='application/pdf')
        validate_image_or_pdf_file(f)  # must not raise

    def test_rejects_garbage(self):
        f = SimpleUploadedFile('doc.jpg', b'not a real file', content_type='image/jpeg')
        with pytest.raises(ValidationError):
            validate_image_or_pdf_file(f)

    def test_rejects_oversized_file(self):
        from employee_truck_control.validators import MAX_IMAGE_BYTES
        oversized = _make_pdf_bytes() + b'0' * MAX_IMAGE_BYTES
        f = SimpleUploadedFile('doc.pdf', oversized, content_type='application/pdf')
        with pytest.raises(ValidationError):
            validate_image_or_pdf_file(f)

    def test_none_is_a_noop(self):
        validate_image_or_pdf_file(None)  # must not raise


class TestValidateImageFileStillRejectsPdf:
    """The plain (non-document) image validator must keep rejecting PDFs --
    only document_photo fields accept them."""

    def test_rejects_pdf(self):
        f = SimpleUploadedFile('doc.pdf', _make_pdf_bytes(), content_type='application/pdf')
        with pytest.raises(ValidationError):
            validate_image_file(f)
