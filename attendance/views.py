from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.views import View

from employees.models import Employee
from attendance.models import PresenceEvent
from attendance.service import AttendanceService


class AttendanceListView(LoginRequiredMixin, View):
    """Per-employee attendance records with optional date filter."""

    template_name = 'attendance/list.html'

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        start_date = self._parse_date(request.GET.get('start_date'))
        end_date = self._parse_date(request.GET.get('end_date'))

        service = AttendanceService()
        records = service.list_records(employee_id=employee.pk, start_date=start_date, end_date=end_date)

        return render(request, self.template_name, {
            'employee': employee,
            'records': records,
            'start_date': start_date,
            'end_date': end_date,
        })

    def delete(self, request, pk):
        return HttpResponseNotAllowed(['GET'], 'Physical deletion of attendance records is not allowed.')

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


class PresenceHistoryView(LoginRequiredMixin, View):
    """
    Global IN/OUT event log.
    - No pk: shows all employees, most recent events first.
    - With ?employee=<pk>: filtered to one employee.
    Supports ?start_date and ?end_date filters.
    """

    template_name = 'attendance/presence_history.html'

    def get(self, request):
        employee_pk = request.GET.get('employee')
        start_date = self._parse_date(request.GET.get('start_date'))
        end_date = self._parse_date(request.GET.get('end_date'))

        qs = PresenceEvent.objects.select_related('employee').order_by('-timestamp')

        employee = None
        if employee_pk:
            employee = get_object_or_404(Employee, pk=employee_pk)
            qs = qs.filter(employee=employee)

        if start_date:
            qs = qs.filter(timestamp__date__gte=start_date)
        if end_date:
            qs = qs.filter(timestamp__date__lte=end_date)

        employees = Employee.objects.filter(is_active=True).order_by('name')

        return render(request, self.template_name, {
            'events': qs,
            'employees': employees,
            'selected_employee': employee,
            'start_date': start_date,
            'end_date': end_date,
        })

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
