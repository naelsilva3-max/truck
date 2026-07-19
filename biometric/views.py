"""
Biometric simulation view.

Allows testing the full IN/OUT attendance flow without physical hardware.

Security:
- Requires login AND staff status (is_staff=True).
- Only available when DEBUG=True — returns 404 in production.
- employee_pk is validated as a positive integer before DB lookup.
"""
import hashlib
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from accounts.logging import log_action
from accounts.mixins import MasterRequiredMixin
from accounts.models import SystemLog
from attendance.models import PresenceEvent
from attendance.service import AttendanceService, next_action_label, presence_label
from biometric.models import BiometricTemplate, KioskDevice, KioskInstallerBuild


class StaffRequiredMixin(UserPassesTestMixin):
    """Allow access only to authenticated staff users."""
    def test_func(self):
        return self.request.user.is_staff


class BiometricSimulatorView(LoginRequiredMixin, StaffRequiredMixin, View):
    template_name = 'biometric/simulator.html'

    def dispatch(self, request, *args, **kwargs):
        # Hard block in production — simulator must never run outside DEBUG
        if not settings.DEBUG:
            raise Http404("Simulator is not available in production.")
        return super().dispatch(request, *args, **kwargs)

    def _enrolled_employees(self):
        rows = []
        for bt in BiometricTemplate.objects.select_related('employee').all():
            # Only expose a short hash — never the raw template bytes
            code = hashlib.sha256(bytes(bt.template)).hexdigest()[:12].upper()
            direction, is_lunch, last_ts = AttendanceService().get_current_status(bt.employee_id)
            rows.append({
                'employee': bt.employee,
                'code': code,
                'direction': direction,
                'last_ts': last_ts,
                'is_in': direction == PresenceEvent.IN,
                'is_lunch': is_lunch,
                'status_label': presence_label(direction, is_lunch),
                'next_action_label': next_action_label(direction, is_lunch),
            })
        rows.sort(key=lambda r: r['employee'].name)
        return rows

    def get(self, request):
        return render(request, self.template_name, {
            'enrolled': self._enrolled_employees(),
            'result': None,
        })

    def post(self, request):
        # Validate employee_pk is a positive integer (prevents IDOR / type confusion)
        raw_pk = request.POST.get('employee_pk', '')
        try:
            employee_pk = int(raw_pk)
            if employee_pk <= 0:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Identificador de funcionário inválido.')
            return redirect('biometric:simulator')

        try:
            bt = BiometricTemplate.objects.select_related('employee').get(
                employee_id=employee_pk
            )
        except BiometricTemplate.DoesNotExist:
            messages.error(request, 'Funcionário não possui biometria cadastrada.')
            return redirect('biometric:simulator')

        from biometric.service import BiometricService, UnavailableBackend
        svc = AttendanceService(
            biometric_service=BiometricService(backend=UnavailableBackend())
        )
        record = svc.process_biometric_event(bytes(bt.template))
        direction, is_lunch, last_ts = svc.get_current_status(bt.employee.pk)

        return render(request, self.template_name, {
            'enrolled': self._enrolled_employees(),
            'result': {
                'employee': bt.employee,
                'direction': direction,
                'last_ts': last_ts,
                'is_in': direction == PresenceEvent.IN,
                'is_lunch': is_lunch,
                'status_label': presence_label(direction, is_lunch),
                'record': record,
            },
        })


class KioskTokenGenerateView(MasterRequiredMixin, View):
    """
    Web equivalent of `python manage.py kiosk_device create --name "..."` —
    lets an admin issue a new kiosk device token from the site instead of
    needing SSH access to the server. The raw token is only ever available
    in the response to the POST that creates it (only its hash is persisted,
    same as the CLI command) -- reloading or revisiting this page never
    shows it again.
    """
    template_name = 'biometric/kiosk_token.html'

    def _devices(self):
        return KioskDevice.objects.order_by('name')

    def get(self, request):
        return render(request, self.template_name, {'devices': self._devices(), 'raw_token': None, 'new_device': None})

    def post(self, request):
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Informe um nome para o quiosque.')
            return render(request, self.template_name, {'devices': self._devices(), 'raw_token': None, 'new_device': None})

        device, raw_token = KioskDevice.issue(name)
        log_action(request, SystemLog.ACTION_UPDATE, f'Token de quiosque gerado: {device.name}')
        return render(request, self.template_name, {
            'devices': self._devices(), 'raw_token': raw_token, 'new_device': device,
        })


class KioskTokenDeleteView(MasterRequiredMixin, View):
    """
    Permanently deletes a KioskDevice row (not just a soft revoke). Any
    kiosk still using this token loses access immediately — biometric
    enroll/scan requests from that machine start failing until it's
    reconfigured with a new token.
    """

    def post(self, request, pk):
        device = get_object_or_404(KioskDevice, pk=pk)
        name = device.name
        device.delete()
        log_action(request, SystemLog.ACTION_DELETE, f'Token de quiosque apagado: {name}')
        messages.success(request, f'Token de "{name}" apagado.')
        return redirect('biometric:kiosk_token')


class KioskInstallerListView(MasterRequiredMixin, View):
    """
    Repositório dos instaladores do quiosque (kiosk_installer/build.ps1
    output): upload de uma nova versão + lista para download em qualquer
    computador onde o ZK9500 será instalado, sem precisar de um canal de
    transferência de arquivo separado (pendrive, e-mail, etc.).
    """
    template_name = 'biometric/kiosk_installer.html'
    MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB — plenty above the ~55MB the exe currently weighs

    def _builds(self):
        return KioskInstallerBuild.objects.select_related('uploaded_by').all()

    def get(self, request):
        return render(request, self.template_name, {'builds': self._builds()})

    def post(self, request):
        version = request.POST.get('version', '').strip()
        notes = request.POST.get('notes', '').strip()
        uploaded_file = request.FILES.get('file')

        if not version or uploaded_file is None:
            messages.error(request, 'Informe a versão e selecione o arquivo do instalador.')
            return redirect('biometric:kiosk_installer')

        if uploaded_file.size > self.MAX_UPLOAD_BYTES:
            messages.error(request, f'Arquivo excede o limite de {self.MAX_UPLOAD_BYTES // (1024 * 1024)}MB.')
            return redirect('biometric:kiosk_installer')

        build = KioskInstallerBuild(
            version=version, notes=notes, file=uploaded_file,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        try:
            build.save()
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return redirect('biometric:kiosk_installer')

        log_action(request, SystemLog.ACTION_CREATE, f'Instalador de quiosque enviado: versão {build.version}')
        messages.success(request, f'Instalador versão {build.version} enviado com sucesso.')
        return redirect('biometric:kiosk_installer')


class KioskInstallerDownloadView(MasterRequiredMixin, View):
    """
    Streams a KioskInstallerBuild's .exe. Mirrors ProtectedMediaView's
    X-Accel-Redirect handoff to nginx in production (so Django doesn't
    buffer a ~55MB file through a worker), but master-gated rather than
    open to any logged-in user, and forces a clean attachment filename
    instead of relying on the browser to guess one from the URL.
    """

    def get(self, request, pk):
        build = get_object_or_404(KioskInstallerBuild, pk=pk)
        filename = f'ZK9500KioskSetup-{build.version}.exe'

        if settings.DEBUG:
            if not build.file.storage.exists(build.file.name):
                raise Http404
            return FileResponse(build.file.open('rb'), as_attachment=True, filename=filename)

        media_root = os.path.realpath(str(settings.MEDIA_ROOT))
        full_path = os.path.realpath(os.path.join(media_root, build.file.name))
        if full_path != media_root and not full_path.startswith(media_root + os.sep):
            raise Http404

        response = HttpResponse()
        response['X-Accel-Redirect'] = '/protected-media/' + build.file.name
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        del response['Content-Type']  # let nginx set it from the file itself
        return response


class KioskInstallerDeleteView(MasterRequiredMixin, View):
    """Removes a KioskInstallerBuild — the DB row and its file on disk."""

    def post(self, request, pk):
        build = get_object_or_404(KioskInstallerBuild, pk=pk)
        version = build.version
        build.file.delete(save=False)
        build.delete()
        log_action(request, SystemLog.ACTION_DELETE, f'Instalador de quiosque removido: versão {version}')
        messages.success(request, f'Instalador versão {version} removido.')
        return redirect('biometric:kiosk_installer')
