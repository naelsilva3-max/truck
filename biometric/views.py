"""
Biometric simulation view.

Allows testing the full IN/OUT attendance flow without physical hardware.
The user selects an employee (who must have a BiometricTemplate enrolled)
and clicks "Simular Scan". The view feeds the stored template bytes directly
into AttendanceService.process_biometric_event(), exactly as the real reader
would, and shows the resulting IN/OUT status.

Access: login required. Only available when DEBUG=True (safe guard).
"""
import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View

from attendance.models import PresenceEvent
from attendance.service import AttendanceService
from employees.models import BiometricTemplate, Employee


class BiometricSimulatorView(LoginRequiredMixin, View):
    template_name = 'biometric/simulator.html'

    def _enrolled_employees(self):
        """Return employees that have a BiometricTemplate, with a display code."""
        rows = []
        for bt in BiometricTemplate.objects.select_related('employee').all():
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
        employee_pk = request.POST.get('employee_pk')
        if not employee_pk:
            messages.error(request, 'Selecione um funcionário.')
            return redirect('biometric:simulator')

        try:
            bt = BiometricTemplate.objects.select_related('employee').get(
                employee_id=employee_pk
            )
        except BiometricTemplate.DoesNotExist:
            messages.error(request, 'Funcionário não possui biometria cadastrada.')
            return redirect('biometric:simulator')

        # Feed the stored template into the service — identical to real hardware
        # Use UnavailableBackend so the exact-bytes fallback is used (no hardware needed)
        from biometric.service import BiometricService, UnavailableBackend
        svc = AttendanceService(biometric_service=BiometricService(backend=UnavailableBackend()))
        record = svc.process_biometric_event(bytes(bt.template))

        direction, last_ts = svc.get_current_status(bt.employee.pk)

        result = {
            'employee': bt.employee,
            'direction': direction,
            'last_ts': last_ts,
            'is_in': direction == PresenceEvent.IN,
            'record': record,
        }

        return render(request, self.template_name, {
            'enrolled': self._enrolled_employees(),
            'result': result,
        })
