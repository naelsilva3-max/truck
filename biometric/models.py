import hashlib
import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from employees.models import Employee


class BiometricTemplate(models.Model):
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='biometric',
        verbose_name='Funcionário',
        help_text='Funcionário associado a este template biométrico.',
    )
    template = models.BinaryField(
        verbose_name='Template',
        help_text='Dados binários do template biométrico (máx. 10 KB).',
    )
    finger_index = models.SmallIntegerField(
        default=0,
        verbose_name='Dedo',
        help_text='Índice do dedo utilizado na captura (0 = padrão).',
    )
    enrolled_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Cadastrado em',
        help_text='Data e hora do cadastro biométrico.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em',
        help_text='Data e hora da última atualização do template.',
    )

    class Meta:
        # Physical table predates this model's move from `employees` to
        # `biometric` — kept as-is so the move touches no data.
        db_table = 'employees_biometrictemplate'
        ordering = ['employee__name']
        verbose_name = 'Template Biométrico'
        verbose_name_plural = 'Templates Biométricos'
        indexes = [
            models.Index(fields=['employee'], name='idx_biotemplate_employee'),
            models.Index(fields=['finger_index'], name='idx_biotemplate_finger'),
        ]

    def __str__(self):
        return f'Template biométrico de {self.employee.name}'

    def clean(self):
        if self.template is None:
            raise ValidationError({'template': 'O template biométrico não pode ser nulo.'})
        # BinaryField stores bytes; support both bytes and memoryview
        template_bytes = bytes(self.template)
        length = len(template_bytes)
        if length == 0:
            raise ValidationError({'template': 'O template biométrico não pode ser vazio (0 bytes).'})
        if length > 10_240:
            raise ValidationError(
                {'template': f'O template biométrico excede o tamanho máximo permitido de 10 KB (tamanho atual: {length} bytes).'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class KioskDevice(models.Model):
    """
    A remote kiosk machine authorized to call the biometric API (enroll,
    template sync, scan report) over the internet using a bearer token.

    Only the token's SHA-256 hash is persisted — the raw token is generated
    and returned exactly once, via `issue()`.
    """

    name = models.CharField(
        max_length=100,
        verbose_name='Nome',
        help_text='Identificação legível do quiosque (ex.: "Recepção - Matriz").',
    )
    token_hash = models.CharField(
        max_length=64, unique=True, editable=False,
        verbose_name='Hash do Token',
    )
    token_prefix = models.CharField(
        max_length=8, editable=False,
        verbose_name='Prefixo do Token',
        help_text='Primeiros caracteres do token, apenas para identificação em logs/admin.',
    )
    is_active = models.BooleanField(default=True, verbose_name='Ativo?')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='Último acesso')
    last_seen_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='Último IP')

    class Meta:
        ordering = ['name']
        verbose_name = 'Dispositivo Quiosque'
        verbose_name_plural = 'Dispositivos Quiosque'
        indexes = [
            models.Index(fields=['token_hash'], name='idx_kioskdevice_token_hash'),
        ]

    def __str__(self):
        return f'{self.name} ({"ativo" if self.is_active else "revogado"})'

    @staticmethod
    def _hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode('ascii')).hexdigest()

    @classmethod
    def issue(cls, name: str) -> tuple['KioskDevice', str]:
        """
        Create a device row and return (device, raw_token).

        raw_token has 256 bits of entropy and is shown to the caller exactly
        once — only its hash is persisted, so it cannot be recovered later.
        """
        raw_token = secrets.token_urlsafe(32)
        device = cls.objects.create(
            name=name,
            token_hash=cls._hash(raw_token),
            token_prefix=raw_token[:8],
        )
        return device, raw_token

    @classmethod
    def authenticate(cls, raw_token: str, ip: str | None = None) -> 'KioskDevice | None':
        """
        Look up an active device by raw token and stamp last_seen_at/last_seen_ip.

        Returns None if the token is empty, unknown, or belongs to a revoked
        device.
        """
        if not raw_token:
            return None
        device = cls.objects.filter(
            token_hash=cls._hash(raw_token), is_active=True,
        ).first()
        if device is None:
            return None
        device.last_seen_at = timezone.now()
        device.last_seen_ip = ip
        device.save(update_fields=['last_seen_at', 'last_seen_ip'])
        return device
