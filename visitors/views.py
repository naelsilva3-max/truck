import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View

from employee_truck_control.http import infinite_scroll_json, is_ajax_request, parse_date_param
from employees.models import Employee
from .forms import VisitorForm, VisitForm
from .models import Visit, Visitor


class VisitorListView(LoginRequiredMixin, View):
    """List all visitors."""
    template_name = 'visitors/list.html'
    PAGE_SIZE = 20
    LIVE_POLL_LIMIT = 50

    def _poll_response(self, request, since):
        since_dt = parse_datetime(since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        if since_dt is None:
            new_visitors = []
        else:
            new_visitors = list(
                Visitor.objects.filter(created_at__gt=since_dt).order_by('-created_at')[:self.LIVE_POLL_LIMIT]
            )

        html = render_to_string('visitors/_visitor_rows.html', {'visitors': new_visitors}, request=request)
        newest = new_visitors[0].created_at.isoformat() if new_visitors else since

        return JsonResponse({'html': html, 'count': len(new_visitors), 'newest': newest})

    def get(self, request):
        from django.core.paginator import Paginator

        since = request.GET.get('since')
        if is_ajax_request(request) and since:
            return self._poll_response(request, since)

        paginator = Paginator(Visitor.objects.all().order_by('name'), self.PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        if is_ajax_request(request):
            return infinite_scroll_json(request, 'visitors/_visitor_rows.html', {'visitors': page_obj}, page_obj)
        return render(request, self.template_name, {'visitors': page_obj, 'page_obj': page_obj})


class VisitorCreateView(LoginRequiredMixin, View):
    """Create a new visitor record."""
    template_name = 'visitors/visitor_form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': VisitorForm(),
            'action': 'Cadastrar',
            'title': 'Novo Visitante',
        })

    def post(self, request):
        form = VisitorForm(request.POST, request.FILES)
        if form.is_valid():
            visitor = form.save()
            messages.success(request, f'Visitante "{visitor.name}" cadastrado com sucesso.')
            return redirect('visitors:list')
        return render(request, self.template_name, {
            'form': form,
            'action': 'Cadastrar',
            'title': 'Novo Visitante',
        })


class VisitorUpdateView(LoginRequiredMixin, View):
    """Edit an existing visitor."""
    template_name = 'visitors/visitor_form.html'

    def get(self, request, pk):
        visitor = get_object_or_404(Visitor, pk=pk)
        return render(request, self.template_name, {
            'form': VisitorForm(instance=visitor),
            'action': 'Salvar',
            'title': f'Editar Visitante — {visitor.name}',
            'visitor': visitor,
        })

    def post(self, request, pk):
        visitor = get_object_or_404(Visitor, pk=pk)
        form = VisitorForm(request.POST, request.FILES, instance=visitor)
        if form.is_valid():
            form.save()
            messages.success(request, f'Visitante "{visitor.name}" atualizado com sucesso.')
            return redirect('visitors:list')
        return render(request, self.template_name, {
            'form': form,
            'action': 'Salvar',
            'title': f'Editar Visitante — {visitor.name}',
            'visitor': visitor,
        })


class VisitorSearchView(LoginRequiredMixin, View):
    """JSON search backing the visitor picker on the visit registration form."""

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return JsonResponse({'results': []})
        visitors = Visitor.objects.filter(
            Q(name__icontains=query) | Q(company__icontains=query) | Q(phone__icontains=query)
        ).order_by('name')[:10]
        return JsonResponse({'results': [
            {'id': v.pk, 'name': v.name, 'company': v.company, 'phone': v.phone}
            for v in visitors
        ]})


class VisitorQuickCreateView(LoginRequiredMixin, View):
    """
    Minimal visitor creation used inline from the visit registration form,
    for a visitor who isn't registered yet. Only name/phone/company — a full
    profile (photos, RG/CPF, etc.) can be filled in later from the visitor's
    own edit page. Reuses VisitorForm so validation (e.g. duplicate name)
    matches the full creation form exactly, minus the RG/CPF requirement.
    """

    def post(self, request):
        form = VisitorForm({
            'name': request.POST.get('name', ''),
            'phone': request.POST.get('phone', ''),
            'company': request.POST.get('company', ''),
        }, require_identity=False)
        if form.is_valid():
            visitor = form.save()
            return JsonResponse({'id': visitor.pk, 'name': visitor.name, 'company': visitor.company, 'phone': visitor.phone})
        return JsonResponse({'errors': form.errors}, status=400)


class VisitListView(LoginRequiredMixin, View):
    """List all visits, with active (on-site) and completed (departed) separated."""
    template_name = 'visitors/visit_list.html'
    PAGE_SIZE = 30

    SEARCH_FIELDS = [
        'visitor__name', 'visitor__company', 'visitor__phone', 'visitor__rg', 'visitor__cpf',
        'responsible__name', 'notes',
    ]

    def get(self, request):
        from django.core.paginator import Paginator
        filter_type = request.GET.get('filter', 'active')
        query = request.GET.get('q', '').strip()

        base_qs = Visit.objects.select_related('visitor', 'responsible').order_by('-visit_date', '-arrival_time')
        active_count = base_qs.filter(actual_departure_time__isnull=True).count()
        completed_count = base_qs.filter(actual_departure_time__isnull=False).count()

        if filter_type == 'active':
            filtered = base_qs.filter(actual_departure_time__isnull=True)
        elif filter_type == 'completed':
            filtered = base_qs.filter(actual_departure_time__isnull=False)
        else:
            filtered = base_qs

        if query:
            search_filter = Q()
            for field in self.SEARCH_FIELDS:
                search_filter |= Q(**{f'{field}__icontains': query})
            filtered = filtered.filter(search_filter)

        paginator = Paginator(filtered, self.PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get('page', 1))

        if is_ajax_request(request):
            return infinite_scroll_json(request, 'visitors/_visit_rows.html', {'visits': page_obj}, page_obj)

        return render(request, self.template_name, {
            'visits': page_obj,
            'page_obj': page_obj,
            'filter_type': filter_type,
            'query': query,
            'active_count': active_count,
            'completed_count': completed_count,
        })


class VisitCreateView(LoginRequiredMixin, View):
    """Register a new visit."""
    template_name = 'visitors/visit_form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': VisitForm(),
            'action': 'Registrar',
            'title': 'Nova Visita',
        })

    def post(self, request):
        form = VisitForm(request.POST)
        if form.is_valid():
            visit = form.save()
            messages.success(
                request,
                f'Visita de "{visit.visitor.name}" registrada para {visit.visit_date} às {visit.arrival_time:%H:%M}.',
            )
            return redirect('visitors:visit_list')
        # Re-render keeps the picked visitor (if any) selected instead of
        # silently reverting to the empty search box.
        selected_visitor = Visitor.objects.filter(pk=request.POST.get('visitor')).first()
        return render(request, self.template_name, {
            'form': form,
            'action': 'Registrar',
            'title': 'Nova Visita',
            'selected_visitor': selected_visitor,
        })


class VisitDetailView(LoginRequiredMixin, View):
    """Show details of a visit."""
    template_name = 'visitors/visit_detail.html'

    def get(self, request, pk):
        visit = get_object_or_404(
            Visit.objects.select_related('visitor', 'responsible'),
            pk=pk,
        )
        return render(request, self.template_name, {'visit': visit})


class VisitDepartView(LoginRequiredMixin, View):
    """Register actual departure time for a visit."""

    def post(self, request, pk):
        visit = get_object_or_404(Visit, pk=pk)
        if visit.actual_departure_time is not None:
            messages.warning(request, f'O visitante "{visit.visitor.name}" já teve a saída registrada.')
            return redirect('visitors:visit_detail', pk=pk)

        now = timezone.localtime(timezone.now())
        # Use update() to bypass model validation (actual departure can be on a different day)
        Visit.objects.filter(pk=visit.pk).update(actual_departure_time=now.time())
        messages.success(
            request,
            f'Saída de "{visit.visitor.name}" registrada às {now:%H:%M}.',
        )
        return redirect('visitors:visit_list')


class VisitBadgePDFView(LoginRequiredMixin, View):
    """Generate a PDF badge for a visit."""

    def get(self, request, pk):
        visit = get_object_or_404(
            Visit.objects.select_related('visitor', 'responsible'),
            pk=pk,
        )

        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas as canvas_module
        import os

        buffer = io.BytesIO()

        # Badge size: vertical/portrait (85mm x 130mm)
        badge_width = 85 * mm
        badge_height = 130 * mm

        c = canvas_module.Canvas(buffer, pagesize=(badge_width, badge_height))

        # Try to register a font with good Unicode support
        font_name = 'Helvetica'
        font_name_bold = 'Helvetica-Bold'
        font_paths = [
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont('CustomFont', fp))
                    font_name = 'CustomFont'
                    font_name_bold = 'CustomFont'
                    break
                except Exception:
                    pass

        # Margins
        margin = 5 * mm
        x_center = badge_width / 2
        w = badge_width - 2 * margin  # 75mm

        # ---- Section 1: Top title ----
        title_y = badge_height - 10 * mm
        c.setFillColor(colors.black)
        c.setFont(font_name_bold, 14)
        c.drawCentredString(x_center, title_y, 'VISITANTE.')

        # ---- Section 2: Circular photo ----
        photo_diameter = 30 * mm
        photo_radius = photo_diameter / 2
        photo_center_y = title_y - 10 * mm - photo_radius

        has_photo = False
        img_path = None
        if visit.visitor.photo and os.path.exists(visit.visitor.photo.path):
            try:
                img_path = visit.visitor.photo.path
                has_photo = True
            except Exception:
                pass

        if has_photo:
            # Draw black circle border (8px ~= 2.1mm at 72dpi, using ~2mm)
            border_width = 0.7 * mm
            c.setStrokeColor(colors.black)
            c.setLineWidth(border_width)
            c.circle(x_center, photo_center_y, photo_radius + border_width / 2, fill=0, stroke=1)

            # Clip to circle and draw image
            c.saveState()
            path = c.beginPath()
            path.circle(x_center, photo_center_y, photo_radius)
            c.clipPath(path, stroke=0)
            c.drawImage(
                img_path,
                x_center - photo_radius,
                photo_center_y - photo_radius,
                width=photo_diameter,
                height=photo_diameter,
                preserveAspectRatio=True,
            )
            c.restoreState()
        else:
            # Draw empty black circle border
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.7 * mm)
            c.circle(x_center, photo_center_y, photo_radius, fill=0, stroke=1)

        # ---- Section 3: Name ----
        name_y = photo_center_y - photo_radius - 6 * mm
        c.setFillColor(colors.black)
        c.setFont(font_name_bold, 12)
        # Wrap long names
        name_text = visit.visitor.name
        max_name_width = w - 2 * mm
        name_line_height = 14
        if c.stringWidth(name_text, font_name_bold, 12) > max_name_width:
            # Try to split into two lines
            words = name_text.split(' ')
            line1 = ''
            line2 = ''
            for word in words:
                test = line1 + ' ' + word if line1 else word
                if c.stringWidth(test, font_name_bold, 12) < max_name_width:
                    line1 = test
                else:
                    line2 = word if not line2 else line2 + ' ' + word
            if line2:
                c.drawCentredString(x_center, name_y, line1.strip())
                c.drawCentredString(x_center, name_y - name_line_height, line2.strip())
                name_y -= name_line_height
            else:
                c.drawCentredString(x_center, name_y, name_text)
        else:
            c.drawCentredString(x_center, name_y, name_text)

        # ---- Section 4: Company ----
        company_y = name_y - 8 * mm
        c.setFont(font_name, 9)
        company_text = visit.visitor.company if visit.visitor.company else ''
        c.drawCentredString(x_center, company_y, company_text)

        # ---- Section 5: Barcode-like pattern ----
        barcode_y = company_y - 14 * mm
        barcode_height = 10 * mm
        barcode_width = w * 0.7
        barcode_x = x_center - barcode_width / 2

        # Draw a simple code-128-like barcode using the visit PK
        code_str = f'{visit.pk:08d}'
        # Generate barcode bars (simple representation)
        import hashlib
        hash_seed = hashlib.md5(code_str.encode()).hexdigest()
        # Draw barcode as vertical bars
        total_bars = 60
        bar_width = barcode_width / total_bars
        bits = ''.join(format(ord(c), '08b') for c in hash_seed[:8])
        # Pad to total_bars
        if len(bits) < total_bars:
            bits = bits.ljust(total_bars, '1')
        else:
            bits = bits[:total_bars]

        for i, bit in enumerate(bits):
            if bit == '1':
                x = barcode_x + i * bar_width
                c.setFillColor(colors.black)
                c.rect(x, barcode_y, bar_width + 0.1 * mm, barcode_height, fill=1, stroke=0)

        # ID text below barcode
        c.setFont(font_name, 7)
        c.drawCentredString(x_center, barcode_y - 4 * mm, f'ID N\u00ba {code_str}')

        # ---- Section 6: Bottom black bar ----
        bar_height = 18 * mm
        bar_y = margin
        c.setFillColor(colors.black)
        c.rect(margin, bar_y, w, bar_height, fill=1, stroke=0)

        # ID in black bar
        c.setFillColor(colors.white)
        c.setFont(font_name_bold, 10)
        c.drawCentredString(x_center, bar_y + bar_height - 6 * mm, f'ID N\u00ba {code_str}')

        # Expiration date
        c.setFont(font_name, 8)
        exp_date = visit.visit_date.strftime('%d/%m/%Y')
        c.drawCentredString(x_center, bar_y + 4 * mm, f'Data de Expira\u00e7\u00e3o: {exp_date}')

        c.showPage()
        c.save()
        buffer.seek(0)

        filename = f'cracha_visitante_{visit.pk}_{visit.visitor.name.replace(" ", "_")}.pdf'
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


class VisitsReportPDFView(LoginRequiredMixin, View):
    """Chronological PDF report of all visits (oldest first), optionally
    restricted to a date range."""

    def get(self, request):
        start_date = parse_date_param(request.GET.get('start_date'))
        end_date = parse_date_param(request.GET.get('end_date'))

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6)
        small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8)

        story = [Paragraph('Relatório de Visitas — Ordem Cronológica', title_style)]

        period_bits = []
        if start_date:
            period_bits.append(f'De {start_date.strftime("%d/%m/%Y")}')
        if end_date:
            period_bits.append(f'Até {end_date.strftime("%d/%m/%Y")}')
        story.append(Paragraph(' — '.join(period_bits) if period_bits else 'Todo o período', styles['Normal']))
        story.append(Paragraph(
            f'Gerado em: {timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")}',
            styles['Normal'],
        ))
        story.append(Spacer(1, 0.5 * cm))

        visits = Visit.objects.select_related('visitor', 'responsible').order_by('visit_date', 'arrival_time')
        if start_date:
            visits = visits.filter(visit_date__gte=start_date)
        if end_date:
            visits = visits.filter(visit_date__lte=end_date)

        if visits:
            table_data = [['Data', 'Chegada', 'Visitante', 'Empresa', 'Responsável', 'Partida', 'Verificado']]
            for v in visits:
                if v.actual_departure_time:
                    partida = v.actual_departure_time.strftime('%H:%M')
                else:
                    partida = f'Prevista {v.scheduled_departure_time.strftime("%H:%M")}'
                table_data.append([
                    v.visit_date.strftime('%d/%m/%Y'),
                    v.arrival_time.strftime('%H:%M'),
                    Paragraph(v.visitor.name, small_style),
                    Paragraph(v.visitor.company or '—', small_style),
                    Paragraph(v.responsible.name, small_style),
                    partida,
                    'Sim' if v.id_verified else 'Não',
                ])
            t = Table(
                table_data,
                colWidths=[2.0 * cm, 1.6 * cm, 3.5 * cm, 3.0 * cm, 3.0 * cm, 2.5 * cm, 1.8 * cm],
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
            story.append(Paragraph(f'Total: {visits.count()} visita(s).', small_style))
        else:
            story.append(Paragraph('<i>Nenhuma visita encontrada para o período selecionado.</i>', small_style))

        doc.build(story)
        buffer.seek(0)

        timestamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="relatorio_visitas_{timestamp}.pdf"'
        return response