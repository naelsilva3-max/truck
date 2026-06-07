import re
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from employees.models import Employee

MERCOSUL_RE = re.compile(r'^[A-Z]{3}[0-9][A-Z][0-9]{2}$')
OLD_PLATE_RE = re.compile(r'^[A-Z]{3}[0-9]{4}$')
CHASSIS_RE = re.compile(r'^[A-Z0-9]{17}$')


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
    name = models.CharField(max_length=100, unique=True, verbose_name='Marca')

    class Meta:
        ordering = ['name']
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'

    def __str__(self):
        return self.name


class TruckModel(models.Model):
    brand = models.ForeignKey(
        TruckBrand,
        on_delete=models.CASCADE,
        related_name='models',
        verbose_name='Marca',
    )
    name = models.CharField(max_length=100, verbose_name='Modelo')

    class Meta:
        ordering = ['brand__name', 'name']
        unique_together = [('brand', 'name')]
        verbose_name = 'Modelo'
        verbose_name_plural = 'Modelos'

    def __str__(self):
        return f'{self.brand.name} {self.name}'


class Truck(models.Model):
    license_plate = models.CharField(max_length=10, unique=True, verbose_name='Placa')
    brand = models.ForeignKey(
        TruckBrand,
        on_delete=models.PROTECT,
        related_name='trucks',
        verbose_name='Marca',
        null=True, blank=True,
    )
    truck_model = models.ForeignKey(
        TruckModel,
        on_delete=models.PROTECT,
        related_name='trucks',
        verbose_name='Modelo',
        null=True, blank=True,
    )
    # Legacy free-text model kept for display/PDF — auto-populated from truck_model
    model = models.CharField(max_length=100, verbose_name='Modelo (texto)', editable=False, default='')
    color = models.CharField(max_length=20, choices=TruckColor.choices, verbose_name='Cor')
    chassis = models.CharField(max_length=17, unique=True, verbose_name='Chassi')
    year = models.IntegerField(null=True, blank=True, verbose_name='Ano')
    is_active = models.BooleanField(default=True, verbose_name='Ativo?')
    photo = models.ImageField(upload_to='trucks/photos/', null=True, blank=True, verbose_name='Foto')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['license_plate']
        verbose_name = 'Caminhão'
        verbose_name_plural = 'Caminhões'

    def __str__(self):
        model_display = str(self.truck_model) if self.truck_model else self.model
        return f'{self.license_plate} — {model_display}'

    def get_model_display(self):
        return str(self.truck_model) if self.truck_model else self.model

    def clean(self):
        if self.license_plate:
            plate = self.license_plate.upper()
            if not (MERCOSUL_RE.match(plate) or OLD_PLATE_RE.match(plate)):
                raise ValidationError({'license_plate': 'Placa inválida. Use o formato Mercosul (ABC1D23) ou antigo (ABC1234).'})

        if self.truck_model and self.brand and self.truck_model.brand_id != self.brand_id:
            raise ValidationError({'truck_model': 'O modelo selecionado não pertence à marca informada.'})

        if not self.truck_model and not self.model.strip():
            raise ValidationError({'truck_model': 'Selecione um modelo.'})

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


class TruckAssignment(models.Model):
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name='assignments')
    driver = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='truck_assignments')
    assigned_at = models.DateTimeField(default=timezone.now)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-assigned_at']
        verbose_name = 'Associação de Motorista'
        verbose_name_plural = 'Associações de Motorista'

    def __str__(self):
        status = 'ativo' if self.unassigned_at is None else 'encerrado'
        return f'{self.truck} ← {self.driver.name} ({status})'

    def clean(self):
        if self.driver_id and not self.driver.is_driver:
            raise ValidationError({'driver': 'O funcionário selecionado não é motorista.'})
        if self.unassigned_at and self.assigned_at and self.unassigned_at < self.assigned_at:
            raise ValidationError({'unassigned_at': 'A data de encerramento não pode ser anterior à data de associação.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.unassigned_at is None:
            qs = TruckAssignment.objects.filter(truck=self.truck, unassigned_at__isnull=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'truck': 'Este caminhão já possui um motorista ativo.'})
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Physical deletion of TruckAssignment is not allowed; use unassigned_at instead.')
