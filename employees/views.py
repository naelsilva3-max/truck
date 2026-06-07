"""
Views for the employees app.

All views require authentication (login_required / LoginRequiredMixin).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    UpdateView,
)

from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.service import BiometricService

from .forms import EmployeeForm
from .models import BiometricTemplate, Employee


# ---------------------------------------------------------------------------
# Employee List
# ---------------------------------------------------------------------------

class EmployeeListView(LoginRequiredMixin, ListView):
    """Lists employees: active first, inactive below. Toggle via ?show_inactive=1."""

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


# ---------------------------------------------------------------------------
# Employee Create
# ---------------------------------------------------------------------------

class EmployeeCreateView(LoginRequiredMixin, CreateView):
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

    def get_success_url(self):
        return reverse_lazy("employees:enroll", kwargs={"pk": self.object.pk})


# ---------------------------------------------------------------------------
# Employee Detail
# ---------------------------------------------------------------------------

class EmployeeDetailView(LoginRequiredMixin, DetailView):
    """Shows employee data and biometric status.

    Returns HTTP 404 if employee not found (Requirement 1.5).
    """

    model = Employee
    template_name = "employees/detail.html"
    context_object_name = "employee"

    def get_object(self, queryset=None):
        try:
            return super().get_object(queryset)
        except Exception:
            raise Http404("Funcionário não encontrado.")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx["has_biometric"] = self.object.biometric is not None
            ctx["biometric_info"] = self.object.biometric
        except BiometricTemplate.DoesNotExist:
            ctx["has_biometric"] = False
            ctx["biometric_info"] = None
        # Current presence status
        from attendance.service import AttendanceService
        from attendance.models import PresenceEvent
        svc = AttendanceService()
        direction, last_ts = svc.get_current_status(self.object.pk)
        ctx["presence_direction"] = direction
        ctx["presence_last_ts"] = last_ts
        ctx["presence_in"] = direction == PresenceEvent.IN
        return ctx


# ---------------------------------------------------------------------------
# Employee Update
# ---------------------------------------------------------------------------

class EmployeeUpdateView(LoginRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = "employees/form.html"

    def get_object(self, queryset=None):
        try:
            return super().get_object(queryset)
        except Exception:
            raise Http404("Funcionário não encontrado.")

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

    def get_success_url(self):
        return reverse_lazy("employees:detail", kwargs={"pk": self.object.pk})


# ---------------------------------------------------------------------------
# Employee Biometric Enrollment
# ---------------------------------------------------------------------------

class EmployeeEnrollView(LoginRequiredMixin, View):
    """Biometric enrollment view for a given employee.

    GET:  Render the enrollment instructions page.
    POST: Capture a fingerprint template via BiometricService; on success,
          upsert BiometricTemplate (create or replace existing).
          Handles device-not-found, capture errors, and invalid template sizes
          without persisting any data (Requirements 2.3, 2.7).

    The BiometricService instance can be injected via the ``biometric_service``
    keyword argument to ``as_view()`` to facilitate testing without real
    hardware.
    """

    template_name = "employees/enroll.html"
    # Maximum allowed template size in bytes (10 KB)
    MAX_TEMPLATE_BYTES = 10_240

    def __init__(self, biometric_service: BiometricService | None = None, **kwargs):
        super().__init__(**kwargs)
        self._biometric_service = biometric_service

    def _get_employee_or_404(self, pk: int) -> Employee:
        try:
            return Employee.objects.get(pk=pk)
        except Employee.DoesNotExist:
            raise Http404("Funcionário não encontrado.")

    def _get_biometric_service(self) -> BiometricService:
        """Return the injected service or a default instance."""
        if self._biometric_service is not None:
            return self._biometric_service
        return BiometricService()

    def get(self, request, pk: int):
        employee = self._get_employee_or_404(pk)
        try:
            _ = employee.biometric
            has_biometric = True
        except BiometricTemplate.DoesNotExist:
            has_biometric = False
        return render(
            request,
            self.template_name,
            {"employee": employee, "has_biometric": has_biometric},
        )

    def post(self, request, pk: int):
        employee = self._get_employee_or_404(pk)

        service = self._get_biometric_service()

        # --- Step 1: Connect to device ---
        try:
            service.connect()
        except BiometricDeviceNotFoundError as exc:
            messages.error(
                request,
                "Leitor biométrico não encontrado. Verifique se o dispositivo ZKTeco ZK9500 "
                "está conectado e tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)

        # --- Step 2: Capture template ---
        template_bytes: bytes | None = None
        try:
            template_bytes = service.capture_template()
        except (BiometricDeviceNotFoundError, BiometricNotConnectedError):
            messages.error(
                request,
                "Leitor biométrico não encontrado ou desconectado durante a captura. "
                "Verifique o dispositivo e tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)
        except TimeoutError:
            messages.error(
                request,
                "Tempo de captura esgotado. Posicione o dedo corretamente no leitor e tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)
        except Exception:
            messages.error(
                request,
                "Erro ao capturar impressão digital. Tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)
        finally:
            # Always release hardware resources after capture attempt
            try:
                service.disconnect()
            except Exception:
                pass

        # --- Step 3: Validate template size (Requirement 2.3) ---
        if template_bytes is None or len(template_bytes) == 0:
            messages.error(
                request,
                "O template biométrico capturado está vazio (0 bytes). "
                "Posicione o dedo corretamente e tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)

        if len(template_bytes) > self.MAX_TEMPLATE_BYTES:
            messages.error(
                request,
                f"O template biométrico capturado excede o tamanho máximo permitido "
                f"de 10 KB ({len(template_bytes)} bytes). Tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)

        # --- Step 4: Upsert BiometricTemplate (Requirement 2.4, 2.5) ---
        try:
            bio, created = BiometricTemplate.objects.get_or_create(
                employee=employee,
                defaults={"template": template_bytes, "finger_index": 0},
            )
            if not created:
                bio.template = template_bytes
                bio.save()
        except Exception:
            messages.error(
                request,
                "Erro ao salvar o template biométrico. Tente novamente.",
            )
            return self._render_with_biometric_status(request, employee)

        action = "cadastrada" if created else "atualizada"
        messages.success(
            request,
            f'Biometria {action} com sucesso para {employee.name}.',
        )
        return redirect("employees:detail", pk=employee.pk)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _render_with_biometric_status(self, request, employee: Employee):
        """Re-render the enrollment page preserving the has_biometric context."""
        try:
            _ = employee.biometric
            has_biometric = True
        except BiometricTemplate.DoesNotExist:
            has_biometric = False
        return render(
            request,
            self.template_name,
            {"employee": employee, "has_biometric": has_biometric},
        )
