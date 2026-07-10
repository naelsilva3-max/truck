from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include

from accounts.views import CPFLoginView
from attendance.views import AttendanceCalendarView, PresenceHistoryView
from employee_truck_control.views import ProtectedMediaView, ReportsIndexView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", CPFLoginView.as_view(), name="login"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/", include("accounts.urls")),
    path("employees/", include("employees.urls")),
    path("employees/", include("attendance.urls")),
    # Global presence history (not employee-scoped)
    path("attendance/presence/", PresenceHistoryView.as_view(), name="presence_history"),
    # Attendance calendar report (pick an employee, browse month by month)
    path("attendance/calendario/", AttendanceCalendarView.as_view(), name="attendance_calendar"),
    # Central hub for every PDF report in the system
    path("relatorios/", ReportsIndexView.as_view(), name="reports_index"),
    path("trucks/", include("trucks.urls")),
    path("biometric/", include("biometric.urls")),
    path("visitors/", include("visitors.urls")),
    # Photos/documents: authenticated users only (see ProtectedMediaView) —
    # replaces Django's DEBUG-only static() media serving and nginx's old
    # public alias, in every environment.
    path("media/<path:path>", ProtectedMediaView.as_view(), name="protected_media"),
    # Redirect root to employee list
    path("", lambda request: redirect("employees:list"), name="root"),
]
