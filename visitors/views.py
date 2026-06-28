import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from employees.models import Employee
from .forms import VisitorForm, VisitForm
from .models import Visit, Visitor


class VisitorListView(LoginRequiredMixin, View):
    """List all visitors."""
    template_name = 'visitors/list.html'

    def get(self, request):
        visitors = Visitor.objects.all().order_by('name')
        return render(request, self.template_name, {'visitors': visitors})


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


class VisitListView(LoginRequiredMixin, View):
    """List all visits, with active (on-site) and completed (departed) separated."""
    template_name = 'visitors/visit_list.html'

    def get(self, request):
        filter_type = request.GET.get('filter', 'all')

        visits_qs = Visit.objects.select_related('visitor', 'responsible').order_by('-visit_date', '-arrival_time')

        if filter_type == 'active':
            visits = [v for v in visits_qs if v.is_active]
        elif filter_type == 'completed':
            visits = [v for v in visits_qs if not v.is_active]
        else:
            visits = list(visits_qs)

        active_visits = [v for v in visits_qs if v.is_active]
        completed_visits = [v for v in visits_qs if not v.is_active]

        return render(request, self.template_name, {
            'visits': visits,
            'active_visits': active_visits,
            'completed_visits': completed_visits,
            'filter_type': filter_type,
            'active_count': len(active_visits),
            'completed_count': len(completed_visits),
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
        return render(request, self.template_name, {
            'form': form,
            'action': 'Registrar',
            'title': 'Nova Visita',
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