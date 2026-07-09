import calendar
from datetime import date, datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View

from employee_truck_control.http import infinite_scroll_json, is_ajax_request, parse_date_param
from employees.models import Employee
from attendance.models import AttendanceRecord, PresenceEvent
from attendance.service import AttendanceService
from visitors.models import Visit


class AttendanceListView(LoginRequiredMixin, View):
    """Per-employee attendance records with optional date filter."""

    template_name = 'attendance/list.html'

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        start_date = parse_date_param(request.GET.get('start_date'))
        end_date = parse_date_param(request.GET.get('end_date'))

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


class AttendanceCalendarView(LoginRequiredMixin, View):
    """
    Monthly calendar report: pick an employee, see every day of the month
    with their check-in/check-out times (one line per AttendanceRecord).
    """

    template_name = 'attendance/calendar.html'

    @staticmethod
    def _to_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get(self, request):
        employee_pk = request.GET.get('employee')
        employee = get_object_or_404(Employee, pk=employee_pk) if employee_pk else None

        today = timezone.localdate()
        year = self._to_int(request.GET.get('year'), today.year)
        month = self._to_int(request.GET.get('month'), today.month)
        if not (1 <= month <= 12):
            month = today.month
        first_of_month = date(year, month, 1)
        last_day_num = calendar.monthrange(year, month)[1]
        last_of_month = date(year, month, last_day_num)

        records_by_day: dict[date, list[AttendanceRecord]] = {}
        if employee:
            records = AttendanceRecord.objects.filter(
                employee=employee, date__gte=first_of_month, date__lte=last_of_month,
            ).order_by('entry_time')
            for record in records:
                records_by_day.setdefault(record.date, []).append(record)

        weeks = []
        for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month):
            weeks.append([
                {
                    'date': day,
                    'in_month': day.month == month,
                    'is_today': day == today,
                    'records': records_by_day.get(day, []),
                }
                for day in week
            ])

        prev_month_date = first_of_month - timedelta(days=1)
        next_month_date = last_of_month + timedelta(days=1)

        return render(request, self.template_name, {
            'employees': Employee.objects.filter(is_active=True).order_by('name'),
            'selected_employee': employee,
            'month_date': first_of_month,
            'weeks': weeks,
            'total_days_worked': len(records_by_day),
            'prev_year': prev_month_date.year,
            'prev_month': prev_month_date.month,
            'next_year': next_month_date.year,
            'next_month': next_month_date.month,
            'today': today,
        })


class PresenceHistoryView(LoginRequiredMixin, View):
    """
    Global IN/OUT event log combining employee presence events and visitor visits.
    Supports ?type=all|employees|visitors filter.
    """

    template_name = 'attendance/presence_history.html'
    PAGE_SIZE = 50

    def _page_size(self, request) -> int:
        """
        Allow AJAX callers (e.g. the employees-list sidebar widget) to request
        a smaller page size than the default full-page PAGE_SIZE, so that
        "load more" continues in the same increments already shown inline.
        Clamped to a sane range; falls back to PAGE_SIZE if absent/invalid.
        """
        raw = request.GET.get('page_size')
        if not raw:
            return self.PAGE_SIZE
        try:
            size = int(raw)
        except ValueError:
            return self.PAGE_SIZE
        return max(1, min(size, 100))

    def get(self, request):
        from django.core.paginator import Paginator
        employee_pk = request.GET.get('employee')
        start_date = parse_date_param(request.GET.get('start_date'))
        end_date = parse_date_param(request.GET.get('end_date'))
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

        events.sort(key=lambda e: e['timestamp'], reverse=True)

        employee = None
        if employee_pk:
            employee = get_object_or_404(Employee, pk=employee_pk)

        employees = Employee.objects.filter(is_active=True).order_by('name')

        paginator = Paginator(events, self._page_size(request))
        page_obj = paginator.get_page(request.GET.get('page', 1))

        if is_ajax_request(request):
            # ?compact=1 is used by the employees-list sidebar widget, which
            # shows only 3 columns (Nome/Data-Hora/Direção) instead of the
            # full history page's 5-column row.
            compact = request.GET.get('compact') == '1'
            row_template = 'employees/_presence_rows.html' if compact else 'attendance/_presence_rows.html'
            return infinite_scroll_json(request, row_template, {'events': page_obj}, page_obj)

        return render(request, self.template_name, {
            'events': page_obj,
            'page_obj': page_obj,
            'employees': employees,
            'selected_employee': employee,
            'start_date': start_date,
            'end_date': end_date,
            'filter_type': filter_type,
        })
