"""
Kiosk-facing JSON API: enroll, template sync, scan report.

These endpoints are called by the standalone kiosk agent (kiosk_agent.py),
never by a browser — auth is a per-device bearer token (biometric/auth.py),
not a Django session. Plain JsonResponse is used throughout, matching this
project's existing convention (see trucks/views.py's TruckModelsJsonView) —
Django REST Framework is intentionally not used here.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from attendance.service import AttendanceService
from biometric.auth import DeviceTokenAuthMixin
from biometric.models import BiometricTemplate
from employees.models import Employee

logger = logging.getLogger(__name__)


def _parse_json(request) -> dict:
    return json.loads(request.body.decode('utf-8'))


@method_decorator(csrf_exempt, name='dispatch')
class KioskEnrollView(DeviceTokenAuthMixin, View):
    """POST {"employee_id": int, "template_b64": str, "finger_index"?: int}"""

    def post(self, request):
        try:
            payload = _parse_json(request)
            employee_id = int(payload['employee_id'])
            template_bytes = base64.b64decode(payload['template_b64'], validate=True)
            finger_index = int(payload.get('finger_index', 0))
        except (KeyError, ValueError, TypeError, json.JSONDecodeError, binascii.Error):
            return JsonResponse({'error': 'bad_request', 'detail': 'Payload malformado.'}, status=400)

        employee = Employee.objects.filter(pk=employee_id).first()
        if employee is None:
            return JsonResponse({'error': 'employee_not_found'}, status=404)

        bio = BiometricTemplate.objects.filter(employee=employee).first()
        created = bio is None
        if bio is None:
            bio = BiometricTemplate(employee=employee, template=template_bytes, finger_index=finger_index)
        else:
            bio.template = template_bytes
            bio.finger_index = finger_index

        try:
            bio.save()  # BiometricTemplate.save() already calls full_clean() — reused, not duplicated.
        except ValidationError as exc:
            return JsonResponse({'error': 'invalid_template', 'detail': exc.message_dict}, status=400)

        logger.info(
            "Kiosk '%s' %s biometria para funcionário %s.",
            self.device.name, 'cadastrou' if created else 'atualizou', employee.pk,
        )
        return JsonResponse({'status': 'ok', 'employee_id': employee.pk, 'created': created})


class KioskTemplateSyncView(DeviceTokenAuthMixin, View):
    """GET → enrolled templates for currently active employees only."""

    def get(self, request):
        qs = (
            BiometricTemplate.objects
            .filter(employee__is_active=True)
            .values_list('employee_id', 'template')
        )
        templates = [
            {'employee_id': emp_id, 'template_b64': base64.b64encode(bytes(tmpl)).decode('ascii')}
            for emp_id, tmpl in qs
        ]
        return JsonResponse({
            'templates': templates,
            'count': len(templates),
            'generated_at': timezone.now().isoformat(),
        })


@method_decorator(csrf_exempt, name='dispatch')
class KioskScanReportView(DeviceTokenAuthMixin, View):
    """POST {"employee_id": int} → IN/OUT toggle for an already-identified employee."""

    def post(self, request):
        try:
            payload = _parse_json(request)
            employee_id = int(payload['employee_id'])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'error': 'bad_request', 'detail': 'Payload malformado.'}, status=400)

        service = AttendanceService()
        try:
            record = service.toggle_for_employee(employee_id)
        except Employee.DoesNotExist:
            return JsonResponse({'error': 'employee_not_found'}, status=404)
        except ValueError as exc:
            return JsonResponse({'error': 'employee_inactive', 'detail': str(exc)}, status=409)

        direction, ts = service.get_current_status(employee_id)
        logger.info("Kiosk '%s' registrou ponto para funcionário %s: %s.", self.device.name, employee_id, direction)
        return JsonResponse({
            'status': 'ok',
            'employee_id': employee_id,
            'direction': direction,
            'timestamp': ts.isoformat() if ts else None,
            'record_id': record.pk,
        })
