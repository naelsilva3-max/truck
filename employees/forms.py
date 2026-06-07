from django import forms
from django.utils import timezone

from .models import Employee


class EmployeeForm(forms.ModelForm):
    """ModelForm for creating and editing Employee records.

    Validates:
    - name: must not be blank or composed only of whitespace (Requirement 1.2)
    - hire_date: must not be a future date (Requirement 1.3)
    """

    class Meta:
        model = Employee
        fields = [
            "name",
            "role",
            "department",
            "phone",
            "hire_date",
            "is_driver",
            "is_active",
            "photo",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nome completo"}
            ),
            "role": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Cargo do funcionário"}
            ),
            "department": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Departamento (opcional)"}
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Telefone (opcional)"}
            ),
            "hire_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"},
                format="%Y-%m-%d",
            ),
            "is_driver": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
        }
        help_texts = {
            "name": "Nome completo do funcionário. Não pode ser vazio.",
            "role": "Cargo ou função exercida pelo funcionário.",
            "department": "Departamento ao qual o funcionário pertence (opcional).",
            "phone": "Telefone de contato do funcionário (opcional).",
            "hire_date": "Data de admissão. Não pode ser uma data futura.",
            "is_driver": "Marque se o funcionário está habilitado a conduzir caminhões.",
            "is_active": "Desmarque para desativar o funcionário (soft-delete).",
        }
        labels = {
            "name": "Nome",
            "role": "Cargo",
            "department": "Departamento",
            "phone": "Telefone",
            "hire_date": "Data de Admissão",
            "is_driver": "É Motorista?",
            "is_active": "Ativo?",
            "photo": "Foto",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure the date input uses ISO format so the HTML date picker works correctly
        self.fields["hire_date"].input_formats = ["%Y-%m-%d"]

    def clean_name(self):
        """Validate that name is not blank or composed only of whitespace.

        Satisfies Requirement 1.2: the system must reject submissions where
        name is empty and display a validation message.
        """
        name = self.cleaned_data.get("name", "")
        if not name or not name.strip():
            raise forms.ValidationError(
                "O nome não pode ser vazio ou composto apenas de espaços."
            )
        return name.strip()

    def clean_hire_date(self):
        """Validate that hire_date is not a future date.

        Satisfies Requirement 1.3: the system must reject submissions where
        hire_date is after today and display a validation message.
        """
        hire_date = self.cleaned_data.get("hire_date")
        if hire_date and hire_date > timezone.now().date():
            raise forms.ValidationError(
                "A data de admissão não pode ser uma data futura."
            )
        return hire_date
