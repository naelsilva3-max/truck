from datetime import date, datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from employees.models import Employee
from attendance.models import PresenceEvent
from attendance.service import AttendanceService
from visitors.models import Visit


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
    Global IN/OUT event log combining employee presence events and visitor visits.
    Supports ?type=all|employees|visitors filter.
    """

    template_name = 'attendance/presence_history.html'

    def get(self, request):
        employee_pk = request.GET.get('employee')
        start_date = self._parse_date(request.GET.get('start_date'))
        end_date = self._parse_date(request.GET.get('end_date'))
        filter_type = request.GET.get('type', 'all')

        events = []

        # Get employee presence events
        if filter_type in ('all', 'employees'):
            qs = PresenceEvent.objects.select_related('employee').order_by('-timestamp')

            if employee_pk:
                employee = get_object_or_404(Employee, pk=employee_pk)
                qs = qs.filter(employee=employee)

            if start_date:
                qs = qs.filter(timestamp__date__gte=start_date)
            if end_date:
                qs = qs.filter(timestamp__date__lte=end_date)

            for pe in qs:
                events.append({
                    'type': 'employee',
                    'employee': pe.employee,
                    'employee_name': pe.employee.name,
                    'timestamp': pe.timestamp,
                    'direction': pe.direction,
                    'attendance_record': pe.attendance_record_id,
                    'visit_pk': None,
                    'visitor_name': None,
                    'company': None,
                })

        # Get visitor visit events
        if filter_type in ('all', 'visitors'):
            visits_qs = Visit.objects.select_related('visitor', 'responsible').order_by('-visit_date', '-arrival_time')

            if start_date:
                visits_qs = visits_qs.filter(visit_date__gte=start_date)
            if end_date:
                visits_qs = visits_qs.filter(visit_date__lte=end_date)

            for v in visits_qs:
                # Arrival event
                arrival_dt = datetime.combine(v.visit_date, v.arrival_time)
                if timezone.is_aware(timezone.now()):
                    arrival_dt = timezone.make_aware(arrival_dt)
                events.append({
                    'type': 'visitor',
                    'employee': None,
                    'employee_name': None,
                    'visitor_name': v.visitor.name,
                    'company': v.visitor.company,
                    'timestamp': arrival_dt,
                    'direction': 'Entrada',
                    'attendance_record': None,
                    'visit_pk': v.pk,
                })

                # Departure event (if actual departure time exists)
                if v.actual_departure_time:
                    depart_dt = datetime.combine(v.visit_date, v.actual_departure_time)
                    if timezone.is_aware(timezone.now()):
                        depart_dt = timezone.make_aware(depart_dt)
                    events.append({
                        'type': 'visitor',
                        'employee': None,
                        'employee_name': None,
                        'visitor_name': v.visitor.name,
                        'company': v.visitor.company,
                        'timestamp': depart_dt,
                        'direction': 'Saída',
                        'attendance_record': None,
                        'visit_pk': v.pk,
                    })

        # Sort all events by timestamp descending
        events.sort(key=lambda e: e['timestamp'], reverse=True)

        employee = None
        if employee_pk:
            employee = get_object_or_404(Employee, pk=employee_pk)

        employees = Employee.objects.filter(is_active=True).order_by('name')

        return render(request, self.template_name, {
            'events': events,
            'employees': employees,
            'selected_employee': employee,
            'start_date': start_date,
            'end_date': end_date,
            'filter_type': filter_type,
        })

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
