from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
# Using get_object_or_404 is more idiomatic Django than custom helper
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.logging import log_action
from accounts.mixins import EditRequiredMixin
from accounts.models import SystemLog
from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.service import BiometricService

from attendance.models import PresenceEvent # Moved from inside method
from attendance.service import AttendanceService # Moved from inside method
from .forms import EmployeeForm
from .models import BiometricTemplate, Employee


class EmployeeListView(LoginRequiredMixin, ListView):
    model = Employee
    template_name = "employees/list.html"
    context_object_name = "employees"

    def get_queryset(self):
        show_inactive = self.request.GET.get('show_inactive') == '1'
        if show_inactive:
            return Employee.objects.order_by('-is_active', 'name')
        return Employee.objects.filter(is_active=True).order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['show_inactive'] = self.request.GET.get('show_inactive') == '1'
        ctx['inactive_count'] = Employee.objects.filter(is_active=False).count()
        return ctx


class EmployeeCreateView(EditRequiredMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "employees/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Criar"
        ctx["title"] = "Novo Funcionário"
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, SystemLog.ACTION_CREATE, f'Funcionário criado: {self.object.name}')
        return response

    def get_success_url(self):
        return reverse_lazy("employees:enroll", kwargs={"pk": self.object.pk})


class EmployeeDetailView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = "employees/detail.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Using hasattr and getattr is cleaner than try/except for OneToOne relations
        ctx["has_biometric"] = hasattr(self.object, 'biometric')
        ctx["biometric_info"] = getattr(self.object, 'biometric', None)
        svc = AttendanceService()
        direction, last_ts = svc.get_current_status(self.object.pk)
        ctx["presence_direction"] = direction
        ctx["presence_last_ts"] = last_ts
        ctx["presence_in"] = direction == PresenceEvent.IN
        return ctx


class EmployeeUpdateView(EditRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "employees/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Salvar"
        ctx["title"] = f"Editar Funcionário — {self.object.name}"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, SystemLog.ACTION_UPDATE, f'Funcionário atualizado: {self.object.name}')
        return response

    def get_success_url(self):
        return reverse_lazy("employees:detail", kwargs={"pk": self.object.pk})


class EmployeeEnrollView(EditRequiredMixin, View):
    template_name = "employees/enroll.html"
    MAX_TEMPLATE_BYTES = 10_240

    def __init__(self, biometric_service: BiometricService | None = None, **kwargs):
        super().__init__(**kwargs)
        self._biometric_service = biometric_service

    def _get_biometric_service(self) -> BiometricService:
        if self._biometric_service is not None:
            return self._biometric_service
        return BiometricService()

    def get(self, request, pk: int):
        employee = get_object_or_404(Employee, pk=pk)
        has_biometric = hasattr(employee, 'biometric') # Check if related object exists
        return render(request, self.template_name, {"employee": employee, "has_biometric": has_biometric})

    def post(self, request, pk: int):
        employee = get_object_or_404(Employee, pk=pk)
        service = self._get_biometric_service()

        try:
            service.connect()
        except BiometricDeviceNotFoundError:
            messages.error(request, "Leitor biométrico não encontrado. Verifique se o dispositivo ZKTeco ZK9500 está conectado e tente novamente.")
            return self._render_with_biometric_status(request, employee)

        template_bytes: bytes | None = None
        try:
            template_bytes = service.capture_template()
        except (BiometricDeviceNotFoundError, BiometricNotConnectedError):
            messages.error(request, "Leitor biométrico não encontrado ou desconectado durante a captura.")
            return self._render_with_biometric_status(request, employee)
        except TimeoutError:
            messages.error(request, "Tempo de captura esgotado. Posicione o dedo corretamente no leitor e tente novamente.")
            return self._render_with_biometric_status(request, employee)
        except Exception:
            messages.error(request, "Erro ao capturar impressão digital. Tente novamente.")
            return self._render_with_biometric_status(request, employee)
        finally:
            try:
                service.disconnect()
            except Exception:
                pass

        if template_bytes is None or len(template_bytes) == 0:
            messages.error(request, "O template biométrico capturado está vazio. Posicione o dedo corretamente e tente novamente.")
            return self._render_with_biometric_status(request, employee)

        if len(template_bytes) > self.MAX_TEMPLATE_BYTES:
            messages.error(request, f"O template biométrico excede o tamanho máximo de 10 KB ({len(template_bytes)} bytes).")
            return self._render_with_biometric_status(request, employee)

        try:
            bio, created = BiometricTemplate.objects.get_or_create(
                employee=employee,
                defaults={"template": template_bytes, "finger_index": 0},
            )
            if not created:
                bio.template = template_bytes
                bio.save()
        except Exception:
            messages.error(request, "Erro ao salvar o template biométrico. Tente novamente.")
            return self._render_with_biometric_status(request, employee)

        action = "cadastrada" if created else "atualizada"
        log_action(request, SystemLog.ACTION_UPDATE, f'Biometria {action} para {employee.name}')
        messages.success(request, f'Biometria {action} com sucesso para {employee.name}.')
        return redirect("employees:detail", pk=employee.pk)

    def _render_with_biometric_status(self, request, employee: Employee):
        # Reuse the logic from the get method to avoid duplication
        # This will re-evaluate has_biometric based on the current state
        return self.get(request, employee.pk)
