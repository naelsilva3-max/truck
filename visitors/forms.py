from django import forms
from django.utils import timezone

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
        ]
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Nome completo'}
            ),
            'photo': forms.ClearableFileInput(
                attrs={'class': 'form-control', 'accept': 'image/*'}
            ),
            'document_photo': forms.ClearableFileInput(
                attrs={'class': 'form-control', 'accept': 'image/*'}
            ),
            'phone': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': '(99) 99999-9999'}
            ),
            'company': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Empresa (opcional)'}
            ),
        }
        labels = {
            'name': 'Nome',
            'photo': 'Foto do Rosto',
            'document_photo': 'Foto do Documento',
            'phone': 'Telefone',
            'company': 'Empresa',
        }
        help_texts = {
            'photo': 'Foto do rosto do visitante.',
            'document_photo': 'Imagem do documento de identificação (RG, CNH, etc.).',
        }

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
            'visitor': forms.Select(attrs={'class': 'form-control'}),
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