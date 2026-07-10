from django import forms
from django.utils import timezone

from employee_truck_control.validators import validate_image_file, validate_image_or_pdf_file
from .models import Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "name", "role", "department", "phone", "rg", "cpf",
            "is_foreigner", "foreign_document_number", "foreign_document_type",
            "address", "cep", "hire_date",
            "is_driver", "is_active", "photo", "document_photo",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nome completo"}),
            "role": forms.TextInput(attrs={"class": "form-control", "placeholder": "Cargo do funcionário"}),
            "department": forms.TextInput(attrs={"class": "form-control", "placeholder": "Departamento (opcional)"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Telefone (opcional)"}),
            "rg": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: 12.345.678-9"}),
            "cpf": forms.TextInput(attrs={"class": "form-control", "placeholder": "000.000.000-00"}),
            "is_foreigner": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_is_foreigner"}),
            "foreign_document_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Número do documento"}),
            "foreign_document_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: Passaporte, RNE"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Rua, número, bairro, cidade"}),
            "cep": forms.TextInput(attrs={"class": "form-control", "placeholder": "00000-000"}),
            "hire_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "is_driver": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "photo": forms.FileInput(attrs={"class": "camera-file-input", "accept": "image/*"}),
            "document_photo": forms.FileInput(attrs={"class": "camera-file-input", "accept": "image/*,application/pdf"}),
        }
        help_texts = {
            "name": "Nome completo do funcionário. Não pode ser vazio.",
            "role": "Cargo ou função exercida pelo funcionário.",
            "department": "Departamento ao qual o funcionário pertence (opcional).",
            "phone": "Telefone de contato do funcionário (opcional).",
            "rg": "Número do RG do funcionário (opcional).",
            "cpf": "CPF do funcionário — validado automaticamente (opcional).",
            "address": "Endereço completo do funcionário (opcional).",
            "cep": "CEP do endereço (opcional).",
            "hire_date": "Data de admissão. Não pode ser uma data futura.",
            "is_driver": "Marque se o funcionário está habilitado a conduzir caminhões.",
            "is_active": "Desmarque para desativar o funcionário (soft-delete).",
            "document_photo": "Imagem ou PDF do documento de identificação (RG, CNH, etc.).",
        }
        labels = {
            "name": "Nome", "role": "Cargo", "department": "Departamento",
            "phone": "Telefone", "rg": "RG", "cpf": "CPF",
            "is_foreigner": "Funcionário estrangeiro (não possui RG/CPF)",
            "foreign_document_number": "Número do Documento",
            "foreign_document_type": "Tipo de Documento",
            "address": "Endereço", "cep": "CEP", "hire_date": "Data de Admissão",
            "is_driver": "É Motorista?", "is_active": "Ativo?",
            "photo": "Foto", "document_photo": "Foto do Documento",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["hire_date"].input_formats = ["%Y-%m-%d"]

    def clean_name(self):
        name = self.cleaned_data.get("name", "")
        if not name or not name.strip():
            raise forms.ValidationError("O nome não pode ser vazio ou composto apenas de espaços.")
        return name.strip()

    def clean_hire_date(self):
        hire_date = self.cleaned_data.get("hire_date")
        if hire_date and hire_date > timezone.now().date():
            raise forms.ValidationError("A data de admissão não pode ser uma data futura.")
        return hire_date

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "read"):
            validate_image_file(photo)
        return photo

    def clean_document_photo(self):
        doc = self.cleaned_data.get("document_photo")
        if doc and hasattr(doc, "read"):
            validate_image_or_pdf_file(doc)
        return doc
