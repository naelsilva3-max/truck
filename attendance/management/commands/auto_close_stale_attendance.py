"""
Management command: auto_close_stale_attendance

Flags AttendanceRecords that have been open (no exit_time) longer than
AttendanceService.MAX_OPEN_DURATION as auto_closed, so an employee who
forgot to scan out — and never scans in again (e.g. left the company,
took leave) — doesn't stay "present" forever in reports/calendars. A scan
that does come back in is caught at scan time by
AttendanceService.toggle_for_employee -> auto_close_if_stale instead; this
command exists for the case where no further scan ever happens.

Meant to run on a schedule (e.g. once a day via cron/systemd timer):
    python manage.py auto_close_stale_attendance
"""
from django.core.management.base import BaseCommand

from attendance.models import AttendanceRecord
from attendance.service import AttendanceService


class Command(BaseCommand):
    help = "Flag AttendanceRecords open longer than MAX_OPEN_DURATION as auto_closed."

    def handle(self, *args, **options):
        service = AttendanceService()
        stale_employee_ids = (
            AttendanceRecord.objects
            .filter(exit_time__isnull=True, auto_closed=False)
            .values_list('employee_id', flat=True)
            .distinct()
        )

        closed = [
            record
            for employee_id in stale_employee_ids
            if (record := service.auto_close_if_stale(employee_id)) is not None
        ]

        if not closed:
            self.stdout.write('Nenhum registro de ponto pendente estava aberto além do limite.')
            return

        for record in closed:
            self.stdout.write(f'Fechado automaticamente: {record}')
        self.stdout.write(self.style.SUCCESS(f'{len(closed)} registro(s) de ponto marcado(s) para revisão.'))
