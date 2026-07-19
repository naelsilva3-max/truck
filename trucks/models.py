import re
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import ProhibitNullCharactersValidator
from django.db import models
from django.utils import timezone

from employees.models import Employee

MERCOSUL_RE = re.compile(r'^[A-Z]{3}[0-9][A-Z][0-9]{2}$')
OLD_PLATE_RE = re.compile(r'^[A-Z]{3}[0-9]{4}$')
CHASSIS_RE = re.compile(r'^[A-Z0-9]{17}$')

# See employees/models.py for why free-text fields need this explicitly.
_no_null_chars = ProhibitNullCharactersValidator()


class TruckColor(models.TextChoices):
    AMARELO  = 'amarelo',  'Amarelo'
    AZUL     = 'azul',     'Azul'
    BEGE     = 'bege',     'Bege'
    BRANCA   = 'branca',   'Branca'
    CINZA    = 'cinza',    'Cinza'
    DOURADA  = 'dourada',  'Dourada'
    GRENA    = 'grena',    'Grená'
    LARANJA  = 'laranja',  'Laranja'
    MARROM   = 'marrom',   'Marrom'
    PRATA    = 'prata',    'Prata'
    PRETA    = 'preta',    'Preta'
    ROSA     = 'rosa',     'Rosa'
    ROXA     = 'roxa',     'Roxa'
    VERDE    = 'verde',    'Verde'
    VERMELHA = 'vermelha', 'Vermelha'
    FANTASIA = 'fantasia', 'Fantasia'


class TruckBrand(models.Model):
    name = models.CharField(
        max_length=100, unique=True,
        verbose_name='Marca',
        help_text='Nome da marca do caminhão (ex.: Volvo, Scania, Mercedes-Benz).',
        validators=[_no_null_chars],
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'
        indexes = [
            models.Index(fields=['name'], name='idx_truckbrand_name'),
        ]

    def __str__(self):
        return self.name


class TruckModel(models.Model):
    brand = models.ForeignKey(
        TruckBrand,
        on_delete=models.CASCADE,
        related_name='models',
        verbose_name='Marca',
        help_text='Marca à qual este modelo pertence.',
    )
    name = models.CharField(
        max_length=100,
        verbose_name='Modelo',
        help_text='Nome do modelo do caminhão (ex.: FH 460, R 440, Actros).',
        validators=[_no_null_chars],
    )

    class Meta:
        ordering = ['brand__name', 'name']
        unique_together = [('brand', 'name')]
        verbose_name = 'Modelo'
        verbose_name_plural = 'Modelos'
        indexes = [
            models.Index(fields=['brand', 'name'], name='idx_truckmodel_brand_name'),
        ]

    def __str__(self):
        return f'{self.brand.name} {self.name}'


class Truck(models.Model):
    license_plate = models.CharField(
        max_length=10, unique=True,
        verbose_name='Placa',
        help_text='Placa do veículo no formato Mercosul (ABC1D23) ou antigo (ABC1234).',
    )
    brand = models.ForeignKey(
        TruckBrand,
        on_delete=models.PROTECT,
        related_name='trucks',
        verbose_name='Marca',
        help_text='Marca do caminhão (preenchida automaticamente pelo modelo).',
        null=True, blank=True,
    )
    truck_model = models.ForeignKey(
        TruckModel,
        on_delete=models.PROTECT,
        related_name='trucks',
        verbose_name='Modelo',
        help_text='Modelo do caminhão.',
    )
    # Legacy free-text model kept for display/PDF — auto-populated from truck_model
    model = models.CharField(
        max_length=100,
        verbose_name='Modelo (texto)',
        editable=False, default='',
        help_text='Texto do modelo preenchido automaticamente (uso interno).',
    )
    color = models.CharField(
        max_length=20, choices=TruckColor.choices,
        verbose_name='Cor',
        help_text='Cor predominante do caminhão.',
    )
    chassis = models.CharField(
        max_length=17, unique=True,
        verbose_name='Chassi',
        help_text='Número do chassi com exatamente 17 caracteres alfanuméricos.',
    )
    year = models.IntegerField(
        null=True, blank=True,
        verbose_name='Ano',
        help_text='Ano de fabricação do caminhão (entre 1900 e o ano atual).',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Ativo?',
        help_text='Indica se o caminhão está ativo para uso/associação.',
    )
    photo = models.ImageField(
        upload_to='trucks/photos/', null=True, blank=True,
        verbose_name='Foto',
        help_text='Foto do caminhão.',
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Observação',
        help_text='Observações adicionais sobre o caminhão (opcional).',
        validators=[_no_null_chars],
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Criado em',
        help_text='Data e hora de criação do registro.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Atualizado em',
        help_text='Data e hora da última atualização do registro.',
    )

    class Meta:
        ordering = ['license_plate']
        verbose_name = 'Caminhão'
        verbose_name_plural = 'Caminhões'
        indexes = [
            models.Index(fields=['license_plate'], name='idx_truck_plate'),
            models.Index(fields=['chassis'], name='idx_truck_chassis'),
            models.Index(fields=['is_active'], name='idx_truck_active'),
            models.Index(fields=['brand', 'truck_model'], name='idx_truck_brand_model'),
        ]

    def __str__(self):
        model_display = str(self.truck_model) if self.truck_model else self.model
        return f'{self.license_plate} — {model_display}'

    def clean(self):
        if self.license_plate:
            plate = self.license_plate.upper()
            if not (MERCOSUL_RE.match(plate) or OLD_PLATE_RE.match(plate)):
                raise ValidationError({'license_plate': 'Placa inválida. Use o formato Mercosul (ABC1D23) ou antigo (ABC1234).'})

        if self.truck_model and self.brand and self.truck_model.brand_id != self.brand_id:
            raise ValidationError({'truck_model': 'O modelo selecionado não pertence à marca informada.'})

        if self.chassis:
            chassis = self.chassis.upper()
            if not CHASSIS_RE.match(chassis):
                raise ValidationError({'chassis': 'O chassi deve ter exatamente 17 caracteres alfanuméricos.'})

        if self.year is not None:
            current_year = date.today().year
            if self.year < 1900 or self.year > current_year:
                raise ValidationError({'year': f'O ano deve estar entre 1900 e {current_year}.'})

    def save(self, *args, **kwargs):
        if self.license_plate:
            self.license_plate = self.license_plate.upper()
        if self.chassis:
            self.chassis = self.chassis.upper()
        if self.truck_model:
            self.brand = self.truck_model.brand
            self.model = str(self.truck_model)
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Physical deletion of Truck is not allowed; use is_active=False instead.')


class TruckPhoto(models.Model):
    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name='Caminhão',
        help_text='Caminhão ao qual esta foto pertence.',
    )
    image = models.ImageField(
        upload_to='trucks/photos/',
        verbose_name='Imagem',
        help_text='Arquivo de imagem do caminhão.',
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name='Ordem',
        help_text='Ordem de exibição da foto (menor = primeiro).',
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Enviado em',
        help_text='Data e hora do upload da foto.',
    )

    class Meta:
        ordering = ['order', 'uploaded_at']
        verbose_name = 'Foto do Caminhão'
        verbose_name_plural = 'Fotos do Caminhão'
        indexes = [
            models.Index(fields=['truck', 'order'], name='idx_truckphoto_truck_order'),
        ]

    def __str__(self):
        return f'Foto {self.order} — {self.truck.license_plate}'

    def delete(self, *args, **kwargs):
        self.image.delete(save=False)
        super().delete(*args, **kwargs)


class TruckAssignment(models.Model):
    truck = models.ForeignKey(
        Truck,
        on_delete=models.PROTECT,
        related_name='assignments',
        verbose_name='Caminhão',
        help_text='Caminhão associado ao motorista.',
    )
    driver = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='truck_assignments',
        verbose_name='Motorista',
        help_text='Funcionário motorista associado ao caminhão.',
    )
    assigned_at = models.DateTimeField(
        default=timezone.now,
        verbose_name='Associado em',
        help_text='Data e hora em que a associação foi criada.',
    )
    unassigned_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Desassociado em',
        help_text='Data e hora em que a associação foi encerrada (nulo = ativa).',
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Observações',
        help_text='Observações adicionais sobre a associação.',
        validators=[_no_null_chars],
    )

    class Meta:
        ordering = ['-assigned_at']
        verbose_name = 'Associação de Motorista'
        verbose_name_plural = 'Associações de Motorista'
        indexes = [
            models.Index(fields=['truck', 'driver'], name='idx_assignment_truck_driver'),
            models.Index(fields=['assigned_at'], name='idx_assignment_assigned_at'),
            models.Index(fields=['unassigned_at'], name='idx_assignment_unassigned_at'),
        ]

    def __str__(self):
        status = 'ativo' if self.unassigned_at is None else 'encerrado'
        return f'{self.truck} ← {self.driver.name} ({status})'

    def clean(self):
        if self.driver_id and not self.driver.is_driver:
            raise ValidationError({'driver': 'O funcionário selecionado não é motorista.'})
        if self.truck_id and not self.truck.is_active:
            raise ValidationError({'truck': 'Não é possível associar motoristas a um caminhão inativo.'})
        # Validate that unassigned_at is not before assigned_at
        if self.unassigned_at and self.assigned_at and self.unassigned_at < self.assigned_at:
            raise ValidationError({'unassigned_at': 'A data de desassociação não pode ser anterior à data de associação.'})
        if self.truck_id and self.unassigned_at is None:
            conflict = TruckAssignment.objects.filter(
                truck_id=self.truck_id, unassigned_at__isnull=True
            ).exclude(pk=self.pk).exists()
            if conflict:
                raise ValidationError({'truck': 'Este caminhão já possui um motorista ativo associado.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Physical deletion of TruckAssignment is not allowed; set unassigned_at instead.')