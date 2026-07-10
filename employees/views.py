import io
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.logging import log_action
from accounts.mixins import EditRequiredMixin
from accounts.models import SystemLog
from biometric.exceptions import BiometricDeviceNotFoundError, BiometricNotConnectedError
from biometric.models import BiometricEnrollRequest, BiometricTemplate
from biometric.service import BiometricService
from employee_truck_control.http import infinite_scroll_json, is_ajax_request

from attendance.models import PresenceEvent
from attendance.service import AttendanceService
from .forms import EmployeeForm
from .models import Employee

logger = logging.getLogger(__name__)


class EmployeeListView(LoginRequiredMixin, ListView):
    model = Employee
    template_name = "employees/list.html"
    context_object_name = "employees"
    paginate_by = 20

    SEARCH_FIELDS = [
        'name', 'role', 'department', 'phone', 'rg', 'cpf',
        'address', 'cep', 'foreign_document_type', 'foreign_document_number',
    ]

    def get_queryset(self):
        show_inactive = self.request.GET.get('show_inactive') == '1'
        if show_inactive:
            queryset = Employee.objects.order_by('-is_active', 'name')
        else:
            queryset = Employee.objects.filter(is_active=True).order_by('name')

        query = self.request.GET.get('q', '').strip()
        if query:
            search_filter = Q()
            for field in self.SEARCH_FIELDS:
                search_filter |= Q(**{f'{field}__icontains': query})
            queryset = queryset.filter(search_filter)
        return queryset

    RECENT_EVENTS_LIMIT = 15

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['show_inactive'] = self.request.GET.get('show_inactive') == '1'
        ctx['query'] = self.request.GET.get('q', '').strip()
        ctx['inactive_count'] = Employee.objects.filter(is_active=False).count()
        # Fetch one extra row to know whether a second page exists, without a
        # separate COUNT(*) query — the extra row is sliced off before display.
        recent_events = list(
            PresenceEvent.objects.select_related('employee')
            .order_by('-timestamp')[:self.RECENT_EVENTS_LIMIT + 1]
        )
        ctx['recent_presence_has_next'] = len(recent_events) > self.RECENT_EVENTS_LIMIT
        ctx['recent_presence_events'] = recent_events[:self.RECENT_EVENTS_LIMIT]
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if is_ajax_request(self.request):
            return infinite_scroll_json(self.request, 'employees/_rows.html', context, context['page_obj'])
        return super().render_to_response(context, **response_kwargs)


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
    # Number of finger samples merged into one enrollment template (ZKTeco-
    # recommended for reliable matching).
    ENROLL_SAMPLES = 3

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
        pending_request = (
            BiometricEnrollRequest.objects
            .filter(employee=employee, status=BiometricEnrollRequest.PENDING)
            .order_by('-requested_at')
            .first()
        )
        if is_ajax_request(request):
            return JsonResponse({
                'waiting': pending_request is not None,
                'has_biometric': has_biometric,
                'request_id': pending_request.pk if pending_request else None,
            })
        return render(request, self.template_name, {
            "employee": employee, "has_biometric": has_biometric, "pending_request": pending_request,
        })

    def post(self, request, pk: int):
        employee = get_object_or_404(Employee, pk=pk)

        if request.POST.get('action') == 'cancel':
            return self._cancel_pending(request, employee)

        service = self._get_biometric_service()

        try:
            service.connect()
        except BiometricDeviceNotFoundError:
            pending_request, created = BiometricEnrollRequest.get_or_create_pending(
                employee=employee,
                requested_by=request.user if request.user.is_authenticated else None,
            )
            if created:
                log_action(request, SystemLog.ACTION_UPDATE, f'Solicitação de biometria remota criada para {employee.name}')
            messages.info(request, "Nenhum leitor local encontrado. Aguardando o quiosque remoto...")
            return self._render_with_biometric_status(request, employee)

        template_bytes: bytes | None = None
        try:
            # Capture several samples of the same finger and merge them into a
            # single robust template (DBMerge).
            template_bytes = service.capture_registration(samples=self.ENROLL_SAMPLES)
        except (BiometricDeviceNotFoundError, BiometricNotConnectedError):
            messages.error(request, "Leitor biométrico não encontrado ou desconectado durante a captura.")
            return self._render_with_biometric_status(request, employee)
        except TimeoutError:
            messages.error(request, "Tempo de captura esgotado. Posicione o dedo corretamente no leitor e tente novamente.")
            return self._render_with_biometric_status(request, employee)
        except Exception:
            logger.exception("Erro inesperado ao capturar biometria para funcionário %s.", employee.pk)
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

    def _cancel_pending(self, request, employee: Employee):
        # Single-statement UPDATE instead of fetch-then-save: races safely
        # against the kiosk API closing the same request via mark_done() —
        # whichever side runs first "wins" the row, the other is a no-op.
        updated = BiometricEnrollRequest.objects.filter(
            employee=employee, status=BiometricEnrollRequest.PENDING,
        ).update(status=BiometricEnrollRequest.CANCELLED, completed_at=timezone.now())
        if updated:
            log_action(request, SystemLog.ACTION_UPDATE, f'Solicitação de biometria remota cancelada para {employee.name}')
            messages.info(request, "Solicitação de cadastro remoto cancelada.")
        return redirect("employees:enroll", pk=employee.pk)


class EmployeeReportPDFView(LoginRequiredMixin, View):
    """PDF report listing all employees (active by default, ?show_inactive=1 to include all)."""

    def get(self, request):
        show_inactive = request.GET.get('show_inactive') == '1'

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6)
        small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8)

        story = [Paragraph('Relatório de Funcionários', title_style)]
        story.append(Paragraph(
            'Incluindo inativos' if show_inactive else 'Somente ativos',
            styles['Normal'],
        ))
        story.append(Paragraph(
            f'Gerado em: {timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")}',
            styles['Normal'],
        ))
        story.append(Spacer(1, 0.5 * cm))

        employees = Employee.objects.order_by('name')
        if not show_inactive:
            employees = employees.filter(is_active=True)

        if employees:
            table_data = [['Nome', 'Cargo', 'Departamento', 'RG', 'CPF', 'Motorista?', 'Admissão', 'Status']]
            for e in employees:
                table_data.append([
                    Paragraph(e.name, small_style),
                    Paragraph(e.role, small_style),
                    Paragraph(e.department or '—', small_style),
                    Paragraph(e.rg or '—', small_style),
                    Paragraph(e.cpf or '—', small_style),
                    'Sim' if e.is_driver else 'Não',
                    e.hire_date.strftime('%d/%m/%Y'),
                    'Ativo' if e.is_active else 'Inativo',
                ])
            t = Table(
                table_data,
                colWidths=[4.2 * cm, 2.8 * cm, 2.8 * cm, 2.6 * cm, 2.8 * cm, 2.0 * cm, 2.3 * cm, 1.9 * cm],
                repeatRows=1,
            )
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1d6fa5')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6f9')]),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dee2e6')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph(f'Total: {employees.count()} funcionário(s).', small_style))
        else:
            story.append(Paragraph('<i>Nenhum funcionário encontrado.</i>', small_style))

        doc.build(story)
        buffer.seek(0)

        timestamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="relatorio_funcionarios_{timestamp}.pdf"'
        return response
