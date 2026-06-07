from django import forms

from employees.models import Employee
from .models import Truck, TruckAssignment, TruckBrand, TruckModel


class TruckForm(forms.ModelForm):
    """Custom form that uses a ChoiceField for truck_model to avoid queryset validation issues."""

    truck_model = forms.ChoiceField(
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

        # Build choices for truck_model: (pk, "Brand Name - Model Name")
        models = TruckModel.objects.select_related('brand').all()
        choices = [('', 'Selecione o modelo')]
        for m in models:
            choices.append((str(m.pk), f'{m.brand.name} - {m.name}'))
        self.fields['truck_model'].choices = choices

        # Set initial value if editing
        if self.instance and self.instance.pk and self.instance.truck_model_id:
            self.initial['truck_model'] = str(self.instance.truck_model_id)

    def clean(self):
        cleaned = super().clean()
        brand = cleaned.get('brand')
        truck_model_pk = cleaned.get('truck_model')

        if truck_model_pk:
            try:
                truck_model_obj = TruckModel.objects.get(pk=truck_model_pk)
                cleaned['truck_model_obj'] = truck_model_obj
                if brand and truck_model_obj.brand_id != brand.pk:
                    self.add_error('truck_model', 'O modelo selecionado não pertence à marca informada.')
            except TruckModel.DoesNotExist:
                self.add_error('truck_model', 'Modelo inválido.')
        else:
            self.add_error('truck_model', 'Selecione um modelo.')

        return cleaned

    def clean_license_plate(self):
        return self.cleaned_data['license_plate'].upper()

    def clean_chassis(self):
        return self.cleaned_data['chassis'].upper()


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