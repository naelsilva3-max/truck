import os

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from trucks.models import Truck

from . import documentation


class ProtectedMediaView(LoginRequiredMixin, View):
    """
    Serves files under MEDIA_ROOT (employee/visitor/truck photos and
    identity documents) to authenticated users only.

    LGPD: these were previously served directly by nginx with no auth check
    at all, so anyone with a guessable/leaked URL could view an RG or CNH
    photo without logging in. Any authenticated user can still view any
    file here (matching the existing page-level access — every detail page
    that shows these photos is itself just LoginRequiredMixin), this view
    only closes the direct-URL bypass around that.

    In production, hands off the actual byte-serving to nginx via
    X-Accel-Redirect (an `internal;`-only nginx location — see
    deploy/nginx.conf) so Django only pays for the auth check, not for
    streaming file contents. In DEBUG (local dev, no nginx in front),
    streams the file directly instead.
    """

    def get(self, request, path):
        media_root = os.path.realpath(str(settings.MEDIA_ROOT))
        full_path = os.path.realpath(os.path.join(media_root, path))
        if full_path != media_root and not full_path.startswith(media_root + os.sep):
            raise Http404  # path traversal attempt (e.g. ../../settings.py)

        if settings.DEBUG:
            if not os.path.isfile(full_path):
                raise Http404
            return FileResponse(open(full_path, 'rb'))

        response = HttpResponse()
        response['X-Accel-Redirect'] = '/protected-media/' + path
        del response['Content-Type']  # let nginx set it from the file itself
        return response


class ReportsIndexView(LoginRequiredMixin, TemplateView):
    """Central hub linking every report available in the system."""

    template_name = 'reports/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['reports'] = [
            {
                'title': 'Calendário de Presença',
                'description': 'Selecione um funcionário para ver suas entradas e saídas do mês em formato de calendário.',
                'url_name': 'attendance_calendar',
                'is_calendar': True,
            },
            {
                'title': 'Relatório de Visitas',
                'description': 'Lista de todas as visitas em ordem cronológica (da mais antiga para a mais recente), com visitante, responsável e horários. Filtre por período ou gere o histórico completo.',
                'url_name': 'visitors:visit_report_pdf',
                'has_date_filter': True,
            },
            {
                'title': 'Relatório de Caminhões',
                'description': 'Lista completa de caminhões cadastrados, com marca, modelo, cor e status. Selecione um caminhão para ver seu histórico de motoristas, ou gere o relatório de todos.',
                'url_name': 'trucks:report_pdf',
                'has_truck_filter': True,
            },
            {
                'title': 'Relatório de Funcionários',
                'description': 'Lista completa de funcionários cadastrados, com cargo, departamento, admissão e status. Inclui apenas ativos por padrão.',
                'url_name': 'employees:report_pdf',
                'has_active_filter': True,
            },
        ]
        ctx['trucks'] = Truck.objects.order_by('license_plate')
        return ctx


class DocumentationIndexView(LoginRequiredMixin, TemplateView):
    """Landing page linking every section of docs/system/ and docs/manual/."""

    template_name = 'documentation/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['nav'] = documentation.nav_tree()
        return ctx


class DocumentationPageView(LoginRequiredMixin, View):
    """Renders one Markdown doc page. `page` defaults to a section's README."""

    def get(self, request, section, page='README'):
        try:
            title, content_html = documentation.render_doc(section, page)
        except documentation.DocNotFound:
            raise Http404
        return render(request, 'documentation/page.html', {
            'title': title,
            'content_html': content_html,
            'section': section,
            'section_label': documentation.SECTION_LABELS.get(section, section),
            'current_page': page,
            'nav': documentation.nav_tree(),
        })
