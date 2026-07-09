"""
Biometric simulation view.

Allows testing the full IN/OUT attendance flow without physical hardware.

Security:
- Requires login AND staff status (is_staff=True).
- Only available when DEBUG=True — returns 404 in production.
- employee_pk is validated as a positive integer before DB lookup.
"""
import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from attendance.models import PresenceEvent
from attendance.service import AttendanceService
from biometric.models import BiometricTemplate


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
            direction, last_ts = AttendanceService().get_current_status(bt.employee_id)
            rows.append({
                'employee': bt.employee,
                'code': code,
                'direction': direction,
                'last_ts': last_ts,
                'is_in': direction == PresenceEvent.IN,
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
        direction, last_ts = svc.get_current_status(bt.employee.pk)

        return render(request, self.template_name, {
            'enrolled': self._enrolled_employees(),
            'result': {
                'employee': bt.employee,
                'direction': direction,
                'last_ts': last_ts,
                'is_in': direction == PresenceEvent.IN,
                'record': record,
            },
        })
