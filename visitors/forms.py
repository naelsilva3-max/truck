from django import forms
from django.utils import timezone

from employee_truck_control.validators import validate_image_file
from employees.models import Employee
from .models import Visitor, Visit


class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = [
            'name',
            'photo',
            'document_photo',
            'phone',
            'company',
            'rg',
            'cpf',
            'is_foreigner',
            'foreign_document_number',
            'foreign_document_type',
        ]
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Nome completo'}
            ),
            'photo': forms.FileInput(
                attrs={'class': 'camera-file-input', 'accept': 'image/*'}
            ),
            'document_photo': forms.FileInput(
                attrs={'class': 'camera-file-input', 'accept': 'image/*'}
            ),
            'phone': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': '(99) 99999-9999'}
            ),
            'company': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Empresa (opcional)'}
            ),
            'rg': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': '00.000.000-0'}
            ),
            'cpf': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': '000.000.000-00'}
            ),
            'is_foreigner': forms.CheckboxInput(
                attrs={'class': 'form-check-input', 'id': 'id_is_foreigner'}
            ),
            'foreign_document_number': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Número do documento'}
            ),
            'foreign_document_type': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Ex.: Passaporte, RNE'}
            ),
        }
        labels = {
            'name': 'Nome',
            'photo': 'Foto do Rosto',
            'document_photo': 'Foto do Documento',
            'phone': 'Telefone',
            'company': 'Empresa',
            'rg': 'RG',
            'cpf': 'CPF',
            'is_foreigner': 'Visitante estrangeiro (não possui RG/CPF)',
            'foreign_document_number': 'Número do Documento',
            'foreign_document_type': 'Tipo de Documento',
        }
        help_texts = {
            'photo': 'Foto do rosto do visitante.',
            'document_photo': 'Imagem do documento de identificação (RG, CNH, etc.).',
            'cpf': 'Validado automaticamente.',
        }

    def __init__(self, *args, require_identity=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_identity = require_identity

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            qs = Visitor.objects.filter(name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Já existe um visitante cadastrado com este nome.')
        return name

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            phone = phone.strip()
            qs = Visitor.objects.filter(phone=phone)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Já existe um visitante cadastrado com este telefone.')
        return phone

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'read'):
            validate_image_file(photo)
        return photo

    def clean_document_photo(self):
        doc = self.cleaned_data.get('document_photo')
        if doc and hasattr(doc, 'read'):
            validate_image_file(doc)
        return doc

    def clean(self):
        cleaned = super().clean()
        if not self.require_identity:
            return cleaned

        is_foreigner = cleaned.get('is_foreigner')
        if is_foreigner:
            if not cleaned.get('foreign_document_number'):
                self.add_error('foreign_document_number', 'Informe o número do documento do visitante estrangeiro.')
            if not cleaned.get('foreign_document_type'):
                self.add_error('foreign_document_type', 'Informe o tipo de documento do visitante estrangeiro.')
        else:
            if not cleaned.get('rg'):
                self.add_error('rg', 'RG é obrigatório (ou marque "Visitante estrangeiro").')
            if not cleaned.get('cpf'):
                self.add_error('cpf', 'CPF é obrigatório (ou marque "Visitante estrangeiro").')
        return cleaned


class VisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = [
            'visitor',
            'visit_date',
            'arrival_time',
            'id_verified',
            'responsible',
            'scheduled_departure_time',
            'notes',
        ]
        widgets = {
            # Driven by a searchable picker (see visit_form.html) instead of
            # a plain <select> — the field itself still holds the visitor id.
            'visitor': forms.HiddenInput(),
            'visit_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'arrival_time': forms.TimeInput(
                attrs={'class': 'form-control', 'type': 'time'},
                format='%H:%M',
            ),
            'id_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'responsible': forms.Select(attrs={'class': 'form-control'}),
            'scheduled_departure_time': forms.TimeInput(
                attrs={'class': 'form-control', 'type': 'time'},
                format='%H:%M',
            ),
            'notes': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Observações (opcional)'}
            ),
        }
        labels = {
            'visitor': 'Visitante',
            'visit_date': 'Data da Visita',
            'arrival_time': 'Hora de Chegada',
            'id_verified': 'Identificação Verificada?',
            'responsible': 'Responsável pela Visita',
            'scheduled_departure_time': 'Hora de Partida (Prevista)',
            'notes': 'Observações',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['visit_date'].input_formats = ['%Y-%m-%d']
        self.fields['visit_date'].initial = timezone.now().date()
        self.fields['arrival_time'].initial = timezone.now().time()
        self.fields['responsible'].queryset = Employee.objects.filter(is_active=True).order_by('name')