import calendar
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View

from accounts.logging import log_action
from accounts.mixins import EditRequiredMixin
from accounts.models import SystemLog
from employee_truck_control.http import infinite_scroll_json, is_ajax_request, parse_date_param
from employees.models import Employee
from attendance.models import AttendanceRecord, PresenceEvent
from attendance.service import AttendanceService
from visitors.models import Visit


class AttendanceListView(LoginRequiredMixin, View):
    """Per-employee attendance records with optional date filter."""

    template_name = 'attendance/list.html'
    LIVE_POLL_LIMIT = 50

    def _filtered_records(self, employee_id, request):
        start_date = parse_date_param(request.GET.get('start_date'))
        end_date = parse_date_param(request.GET.get('end_date'))
        return AttendanceService().list_records(employee_id=employee_id, start_date=start_date, end_date=end_date)

    def _poll_response(self, employee_id, request, since):
        """New check-ins (brand-new AttendanceRecord rows) since `since`."""
        since_dt = parse_datetime(since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        if since_dt is None:
            new_records = []
        else:
            new_records = list(
                self._filtered_records(employee_id, request)
                .filter(created_at__gt=since_dt).order_by('-created_at')[:self.LIVE_POLL_LIMIT]
            )

        html = render_to_string('attendance/_record_rows.html', {'records': new_records}, request=request)
        newest = new_records[0].created_at.isoformat() if new_records else since

        return JsonResponse({'html': html, 'count': len(new_records), 'newest': newest})

    def _update_response(self, employee_id, request, changed_since):
        """A record that already exists gets its exit_time filled in later
        (checkout), on the same row created at check-in — that's the case
        this catches, via AttendanceRecord.updated_at."""
        since_dt = parse_datetime(changed_since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        if since_dt is None:
            changed_records = []
        else:
            changed_records = list(
                self._filtered_records(employee_id, request)
                .filter(updated_at__gt=since_dt).order_by('-updated_at')[:self.LIVE_POLL_LIMIT]
            )

        html = render_to_string('attendance/_record_rows.html', {'records': changed_records}, request=request)
        newest = changed_records[0].updated_at.isoformat() if changed_records else changed_since

        return JsonResponse({'html': html, 'count': len(changed_records), 'newest': newest, 'removed_ids': []})

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)

        if is_ajax_request(request):
            since = request.GET.get('since')
            if since:
                return self._poll_response(employee.pk, request, since)
            changed_since = request.GET.get('changed_since')
            if changed_since:
                return self._update_response(employee.pk, request, changed_since)

        records = self._filtered_records(employee.pk, request)
        start_date = parse_date_param(request.GET.get('start_date'))
        end_date = parse_date_param(request.GET.get('end_date'))

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

    def _update_response(self, employee, first_of_month, last_of_month, request, changed_since):
        """
        Live-update endpoint for the calendar grid: given the employee and
        visible month already on screen, returns just the day cells whose
        AttendanceRecord set changed (new check-in OR a checkout closing an
        already-visible open record) after `changed_since`, so the client
        can patch only those cells in place. The grid has no single
        table/tbody to hook the shared startLivePoll/startLiveUpdate onto
        (it's a month of day divs, not rows), hence this bespoke endpoint
        + window.startCalendarLiveUpdate in base.html.
        """
        since_dt = parse_datetime(changed_since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        days_html = {}
        newest = changed_since
        if since_dt is not None:
            changed_records = list(
                AttendanceRecord.objects.filter(
                    employee=employee, date__gte=first_of_month, date__lte=last_of_month,
                ).filter(Q(created_at__gt=since_dt) | Q(updated_at__gt=since_dt)).order_by('entry_time')
            )
            if changed_records:
                changed_days: dict[date, list[AttendanceRecord]] = {}
                for record in changed_records:
                    changed_days.setdefault(record.date, []).append(record)

                for day, day_records in changed_days.items():
                    # Re-render the FULL day (not just the changed record),
                    # since the client replaces the whole cell's contents —
                    # a day can have more than one record (e.g. two shifts).
                    all_records_that_day = AttendanceRecord.objects.filter(
                        employee=employee, date=day,
                    ).order_by('entry_time')
                    days_html[day.isoformat()] = render_to_string(
                        'attendance/_calendar_day_records.html', {'records': all_records_that_day}, request=request
                    )

                latest_ts = max(
                    max(r.created_at, r.updated_at) for r in changed_records
                )
                newest = latest_ts.isoformat()

        return JsonResponse({'days': days_html, 'newest': newest})

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

        changed_since = request.GET.get('changed_since')
        if employee and changed_since and is_ajax_request(request):
            return self._update_response(employee, first_of_month, last_of_month, request, changed_since)

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
    LIVE_POLL_LIMIT = 50

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

    def _poll_response(self, request, events, since):
        """
        Live-update endpoint: given `since` (an ISO timestamp of the newest
        event the client already has), return only strictly newer events as
        rendered row HTML, so the client can prepend them without a reload.
        """
        since_dt = parse_datetime(since)
        if since_dt is not None and timezone.is_naive(since_dt):
            since_dt = timezone.make_aware(since_dt)

        if since_dt is None:
            new_events = []
        else:
            new_events = [e for e in events if e['timestamp'] > since_dt][:self.LIVE_POLL_LIMIT]

        compact = request.GET.get('compact') == '1'
        row_template = 'employees/_presence_rows.html' if compact else 'attendance/_presence_rows.html'
        html = render_to_string(row_template, {'events': new_events}, request=request)
        newest = new_events[0]['timestamp'].isoformat() if new_events else since

        return JsonResponse({'html': html, 'count': len(new_events), 'newest': newest})

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

        since = request.GET.get('since')
        if is_ajax_request(request) and since:
            return self._poll_response(request, events, since)

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


class AttendancePendingReviewView(EditRequiredMixin, View):
    """
    Records the system auto-closed because the employee never scanned out
    within AttendanceService.MAX_OPEN_DURATION (see
    AttendanceService.auto_close_if_stale). An admin/master fills in the
    real exit time here; the record drops off this list once exit_time is
    set (still flagged auto_closed=True as an audit trail of what happened).
    """

    template_name = 'attendance/pending_review.html'

    def _pending(self):
        return (
            AttendanceRecord.objects
            .filter(auto_closed=True, exit_time__isnull=True)
            .select_related('employee')
            .order_by('entry_time')
        )

    def get(self, request, pk=None):
        return render(request, self.template_name, {'records': self._pending()})

    def post(self, request, pk):
        record = get_object_or_404(AttendanceRecord, pk=pk, auto_closed=True, exit_time__isnull=True)
        exit_time = parse_datetime(request.POST.get('exit_time', ''))
        if exit_time is not None and timezone.is_naive(exit_time):
            exit_time = timezone.make_aware(exit_time)

        if exit_time is None:
            messages.error(request, 'Informe uma data/hora de saída válida.')
            return redirect('attendance:pending_review')

        record.exit_time = exit_time
        try:
            record.save()
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return redirect('attendance:pending_review')

        log_action(
            request, SystemLog.ACTION_UPDATE,
            f'Saída corrigida manualmente para {record.employee.name} '
            f'(registro de {record.date}, fechado automaticamente por falta de batida de saída).',
        )
        messages.success(request, f'Saída de {record.employee.name} registrada com sucesso.')
        return redirect('attendance:pending_review')
