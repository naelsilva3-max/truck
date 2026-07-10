"""
Shared validators for the project.
"""
import re

from django.core.exceptions import ValidationError

# Allowed image magic bytes: JPEG, PNG, GIF, WEBP
_IMAGE_SIGNATURES = [
    (b'\xff\xd8\xff', 'JPEG'),
    (b'\x89PNG\r\n\x1a\n', 'PNG'),
    (b'GIF87a', 'GIF'),
    (b'GIF89a', 'GIF'),
    (b'RIFF', 'WEBP'),  # WEBP starts with RIFF....WEBP
]

MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

_PDF_SIGNATURE = b'%PDF-'


def _matches_image_signature(header: bytes) -> bool:
    for signature, fmt in _IMAGE_SIGNATURES:
        if header[:len(signature)] == signature:
            # Extra check for WEBP: bytes 8-12 must be b'WEBP'
            if fmt == 'WEBP' and header[8:12] != b'WEBP':
                continue
            return True
    return False


def validate_image_file(file):
    """
    Validate that an uploaded file is a real image by checking magic bytes,
    and that it does not exceed the maximum allowed size.

    Raises ValidationError for:
    - Files larger than MAX_IMAGE_SIZE_MB
    - Files whose content does not match any known image signature
    """
    if file is None:
        return

    # Size check
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError(
            f'O arquivo é muito grande ({file.size // (1024*1024)} MB). '
            f'O tamanho máximo permitido é {MAX_IMAGE_SIZE_MB} MB.'
        )

    # Magic bytes check — read first 12 bytes without consuming the stream
    file.seek(0)
    header = file.read(12)
    file.seek(0)

    if _matches_image_signature(header):
        return

    raise ValidationError(
        'O arquivo enviado não é uma imagem válida. '
        'Formatos aceitos: JPEG, PNG, GIF, WEBP.'
    )


def validate_image_or_pdf_file(file):
    """
    Same as validate_image_file, but also accepts a real PDF (checked via
    its %PDF- magic bytes). Used for document photos, which may be either a
    photographed ID (image) or a scanned document (PDF).
    """
    if file is None:
        return

    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError(
            f'O arquivo é muito grande ({file.size // (1024*1024)} MB). '
            f'O tamanho máximo permitido é {MAX_IMAGE_SIZE_MB} MB.'
        )

    file.seek(0)
    header = file.read(12)
    file.seek(0)

    if header[:len(_PDF_SIGNATURE)] == _PDF_SIGNATURE:
        return
    if _matches_image_signature(header):
        return

    raise ValidationError(
        'O arquivo enviado não é uma imagem nem um PDF válido. '
        'Formatos aceitos: JPEG, PNG, GIF, WEBP, PDF.'
    )


def validate_cpf(value: str) -> None:
    """
    Validate a Brazilian CPF using its standard check-digit algorithm.
    Accepts any punctuation (123.456.789-00 or 12345678900) — only the
    11 digits matter.
    """
    if not value:
        return
    digits = re.sub(r'\D', '', value)
    if len(digits) != 11 or digits == digits[0] * 11:
        raise ValidationError('CPF inválido.')

    for position in (9, 10):
        total = sum(int(digits[i]) * (position + 1 - i) for i in range(position))
        check_digit = (total * 10 % 11) % 10
        if check_digit != int(digits[position]):
            raise ValidationError('CPF inválido.')


def validate_cep(value: str) -> None:
    """Validate a Brazilian CEP: exactly 8 digits, any punctuation accepted."""
    if not value:
        return
    digits = re.sub(r'\D', '', value)
    if len(digits) != 8:
        raise ValidationError('CEP inválido. Use o formato 99999-999.')
