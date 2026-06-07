import io
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from employees.models import Employee
from .forms import TruckAssignmentForm, TruckForm
from .models import Truck, TruckAssignment, TruckBrand, TruckModel


# ---------------------------------------------------------------------------
# TruckManager helpers
# ---------------------------------------------------------------------------

def get_current_driver(truck_id: int) -> Employee | None:
    assignment = TruckAssignment.objects.filter(
        truck_id=truck_id, unassigned_at__isnull=True
    ).select_related('driver').first()
    return assignment.driver if assignment else None


def list_assignments(truck_id: int):
    return TruckAssignment.objects.filter(truck_id=truck_id).select_related('driver')


# ---------------------------------------------------------------------------
# Brand/Model management + JSON API
# ---------------------------------------------------------------------------

class TruckModelsJsonView(LoginRequiredMixin, View):
    """Return JSON list of models for a given brand — used by the form JS."""
    def get(self, request, brand_pk):
        models = TruckModel.objects.filter(brand_id=brand_pk).values('pk', 'name')
        return JsonResponse(list(models), safe=False)


class TruckBrandModelManageView(LoginRequiredMixin, View):
    """Simple page to create brands and models."""
    template_name = 'trucks/brands.html'

    def get(self, request):
        return render(request, self.template_name, {
            'brands': TruckBrand.objects.prefetch_related('models').all(),
        })

    def post(self, request):
        action = request.POST.get('action')
        if action == 'add_brand':
            name = request.POST.get('brand_name', '').strip()
            if name:
                TruckBrand.objects.get_or_create(name=name)
                messages.success(request, f'Marca "{name}" cadastrada.')
            else:
                messages.error(request, 'Nome da marca não pode ser vazio.')
        elif action == 'add_model':
            brand_pk = request.POST.get('brand_pk')
            name = request.POST.get('model_name', '').strip()
            if brand_pk and name:
                brand = get_object_or_404(TruckBrand, pk=brand_pk)
                TruckModel.objects.get_or_create(brand=brand, name=name)
                messages.success(request, f'Modelo "{name}" adicionado à marca "{brand.name}".')
            else:
                messages.error(request, 'Selecione a marca e informe o modelo.')
        elif action == 'delete_brand':
            brand_pk = request.POST.get('brand_pk')
            brand = get_object_or_404(TruckBrand, pk=brand_pk)
            if brand.trucks.exists():
                messages.error(request, f'Marca "{brand.name}" possui caminhões e não pode ser removida.')
            else:
                brand.delete()
                messages.success(request, 'Marca removida.')
        elif action == 'delete_model':
            model_pk = request.POST.get('model_pk')
            tm = get_object_or_404(TruckModel, pk=model_pk)
            if tm.trucks.exists():
                messages.error(request, f'Modelo "{tm}" possui caminhões e não pode ser removido.')
            else:
                tm.delete()
                messages.success(request, 'Modelo removido.')
        return redirect('trucks:brands')


# ---------------------------------------------------------------------------
# CRUD views
# ---------------------------------------------------------------------------

class TruckListView(LoginRequiredMixin, View):
    def get(self, request):
        trucks = Truck.objects.all()
        trucks_with_driver = [(truck, get_current_driver(truck.pk)) for truck in trucks]
        return render(request, 'trucks/list.html', {'trucks_with_driver': trucks_with_driver})


class TruckCreateView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'trucks/form.html', {
            'form': TruckForm(), 'action': 'Cadastrar',
        })

    def post(self, request):
        form = TruckForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                truck = form.save()
                messages.success(request, f'Caminhão {truck.license_plate} cadastrado com sucesso.')
                return redirect('trucks:detail', pk=truck.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
        return render(request, 'trucks/form.html', {
            'form': form, 'action': 'Cadastrar',
        })


class TruckDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        return render(request, 'trucks/detail.html', {
            'truck': truck,
            'current_driver': get_current_driver(pk),
            'assignments': list_assignments(pk),
            'assign_form': TruckAssignmentForm(),
        })


class TruckUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        return render(request, 'trucks/form.html', {
            'form': TruckForm(instance=truck),
            'action': 'Salvar',
            'truck': truck,
        })

    def post(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        form = TruckForm(request.POST, request.FILES, instance=truck)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Caminhão atualizado com sucesso.')
                return redirect('trucks:detail', pk=pk)
            except ValidationError as exc:
                form.add_error(None, exc)
        return render(request, 'trucks/form.html', {
            'form': form, 'action': 'Salvar', 'truck': truck,
        })


# ---------------------------------------------------------------------------
# Assignment views
# ---------------------------------------------------------------------------

class AssignDriverView(LoginRequiredMixin, View):
    def post(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        form = TruckAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.truck = truck
            assignment.assigned_at = timezone.now()
            try:
                assignment.save()
                messages.success(request, f'Motorista {assignment.driver.name} associado ao caminhão {truck.license_plate}.')
            except (ValidationError, Exception) as exc:
                messages.error(request, str(exc))
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
        return redirect('trucks:detail', pk=pk)


class UnassignDriverView(LoginRequiredMixin, View):
    def post(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        assignment = TruckAssignment.objects.filter(
            truck=truck, unassigned_at__isnull=True
        ).first()
        if assignment is None:
            messages.error(request, 'Este caminhão não possui motorista ativo.')
        else:
            TruckAssignment.objects.filter(pk=assignment.pk).update(unassigned_at=timezone.now())
            messages.success(request, f'Motorista {assignment.driver.name} desassociado do caminhão {truck.license_plate}.')
        return redirect('trucks:detail', pk=pk)


class AssignmentHistoryView(LoginRequiredMixin, View):
    def get(self, request, pk):
        truck = get_object_or_404(Truck, pk=pk)
        assignments = list_assignments(pk)
        return render(request, 'trucks/assignments.html', {'truck': truck, 'assignments': assignments})

    def delete(self, request, pk):
        return HttpResponseNotAllowed(
            permitted_methods=['GET'],
            content='Physical deletion of TruckAssignment is not allowed.',
        )


class GlobalAssignmentHistoryView(LoginRequiredMixin, View):
    """Global driver-assignment history across all trucks, with filters."""

    def get(self, request):
        from datetime import date
        truck_pk = request.GET.get('truck')
        driver_pk = request.GET.get('driver')
        start_date = self._parse_date(request.GET.get('start_date'))
        end_date = self._parse_date(request.GET.get('end_date'))

        qs = TruckAssignment.objects.select_related('truck', 'driver').order_by('-assigned_at')

        selected_truck = None
        selected_driver = None
        if truck_pk:
            selected_truck = get_object_or_404(Truck, pk=truck_pk)
            qs = qs.filter(truck=selected_truck)
        if driver_pk:
            from employees.models import Employee as _Employee
            selected_driver = get_object_or_404(_Employee, pk=driver_pk)
            qs = qs.filter(driver=selected_driver)
        if start_date:
            qs = qs.filter(assigned_at__date__gte=start_date)
        if end_date:
            qs = qs.filter(assigned_at__date__lte=end_date)

        from employees.models import Employee as _Employee
        trucks = Truck.objects.order_by('license_plate')
        drivers = _Employee.objects.filter(is_driver=True).order_by('name')

        return render(request, 'trucks/global_assignments.html', {
            'assignments': qs,
            'trucks': trucks,
            'drivers': drivers,
            'selected_truck': selected_truck,
            'selected_driver': selected_driver,
            'start_date': start_date,
            'end_date': end_date,
        })

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            from datetime import date
            return date.fromisoformat(value)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# PDF Report view
# ---------------------------------------------------------------------------

class TruckReportPDFView(LoginRequiredMixin, View):
    def get(self, request):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title', parent=styles['Title'],
            fontSize=16, spaceAfter=12,
        )
        section_style = ParagraphStyle(
            'Section', parent=styles['Heading2'],
            fontSize=12, spaceBefore=12, spaceAfter=4,
            textColor=colors.HexColor('#1d6fa5'),
        )
        small_style = ParagraphStyle(
            'Small', parent=styles['Normal'], fontSize=8,
        )

        story = []
        story.append(Paragraph('Relatório de Caminhões e Histórico de Associações', title_style))
        story.append(Paragraph(
            f'Gerado em: {timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")}',
            styles['Normal'],
        ))
        story.append(Spacer(1, 0.5 * cm))

        trucks = Truck.objects.prefetch_related('assignments__driver').order_by('license_plate')

        for truck in trucks:
            # Truck header
            status = 'Ativo' if truck.is_active else 'Inativo'
            color_display = truck.get_color_display()
            story.append(Paragraph(
                f'{truck.license_plate} — {truck.model} | {color_display} | {status}',
                section_style,
            ))
            if truck.year:
                story.append(Paragraph(f'Ano: {truck.year} | Chassi: {truck.chassis}', small_style))
            else:
                story.append(Paragraph(f'Chassi: {truck.chassis}', small_style))

            assignments = truck.assignments.all()
            if assignments:
                table_data = [['Motorista', 'Início', 'Fim', 'Observações']]
                for a in assignments:
                    fim = a.unassigned_at.strftime('%d/%m/%Y %H:%M') if a.unassigned_at else 'Ativo'
                    table_data.append([
                        Paragraph(a.driver.name, small_style),
                        a.assigned_at.strftime('%d/%m/%Y %H:%M'),
                        fim,
                        Paragraph(a.notes or '—', small_style),
                    ])
                t = Table(
                    table_data,
                    colWidths=[4.5 * cm, 3.5 * cm, 3.5 * cm, 5.5 * cm],
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
            else:
                story.append(Paragraph('<i>Sem associações registradas.</i>', small_style))

            story.append(Spacer(1, 0.4 * cm))

        doc.build(story)
        buffer.seek(0)

        filename = f'relatorio_caminhoes_{timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")}.pdf'
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
