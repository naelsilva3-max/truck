from django import forms

from employees.models import Employee
from .models import Truck, TruckAssignment, TruckBrand, TruckModel


class TruckForm(forms.ModelForm):
    """Custom form that uses a ChoiceField for truck_model to avoid validation issues."""

    truck_model = forms.ModelChoiceField(
        queryset=TruckModel.objects.all(),
        label='Modelo',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_truck_model'}),
    )

    class Meta:
        model = Truck
        fields = ['license_plate', 'brand', 'truck_model', 'color', 'chassis', 'year', 'is_active', 'photo']
        labels = {
            'license_plate': 'Placa',
            'brand': 'Marca',
            'truck_model': 'Modelo',
            'color': 'Cor',
            'chassis': 'Chassi',
            'year': 'Ano',
            'is_active': 'Ativo?',
            'photo': 'Foto',
        }
        widgets = {
            'license_plate': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: ABC1D23 ou ABC1234',
                'style': 'text-transform:uppercase',
            }),
            'brand': forms.Select(attrs={'class': 'form-control', 'id': 'id_brand'}),
            'color': forms.Select(attrs={'class': 'form-control'}),
            'chassis': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '17 caracteres alfanuméricos',
                'maxlength': '17',
                'style': 'text-transform:uppercase',
                'oninput': 'this.value=this.value.replace(/[^A-Za-z0-9]/g,"").toUpperCase().slice(0,17)',
            }),
            'year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 2022'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['brand'].queryset = TruckBrand.objects.all()
        self.fields['brand'].empty_label = 'Selecione a marca'

        self.fields['truck_model'].queryset = TruckModel.objects.select_related('brand').all().order_by('brand__name', 'name')
        self.fields['truck_model'].empty_label = 'Selecione o modelo'
        self.fields['truck_model'].label_from_instance = lambda obj: f'{obj.brand.name} - {obj.name}'

    def clean(self):
        cleaned = super().clean()
        brand = cleaned.get('brand')
        truck_model = cleaned.get('truck_model')

        if truck_model and brand and truck_model.brand_id != brand.pk:
            self.add_error('truck_model', 'O modelo selecionado não pertence à marca informada.')

        return cleaned

    def clean_license_plate(self):
        plate = self.cleaned_data.get('license_plate')
        return plate.upper() if plate else plate

    def clean_chassis(self):
        chassis = self.cleaned_data.get('chassis')
        return chassis.upper() if chassis else chassis


class TruckAssignmentForm(forms.ModelForm):
    class Meta:
        model = TruckAssignment
        fields = ['driver', 'notes']
        labels = {'driver': 'Motorista', 'notes': 'Observações'}
        widgets = {
            'driver': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['driver'].queryset = Employee.objects.filter(is_driver=True, is_active=True)