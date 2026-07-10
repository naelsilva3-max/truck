"""
URL configuration for the employees app.

Namespace: employees

Routes
------
  /employees/                     → EmployeeListView    (employees:list)
  /employees/new/                 → EmployeeCreateView  (employees:create)
  /employees/<pk>/                → EmployeeDetailView  (employees:detail)
  /employees/<pk>/edit/           → EmployeeUpdateView  (employees:update)
  /employees/<pk>/enroll/         → EmployeeEnrollView  (employees:enroll)
  /employees/<pk>/biometric/delete/ → EmployeeDeleteBiometricView (employees:biometric_delete)
  /employees/report/pdf/          → EmployeeReportPDFView (employees:report_pdf)
"""

from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    # List all employees
    path("", views.EmployeeListView.as_view(), name="list"),

    # Create a new employee
    path("new/", views.EmployeeCreateView.as_view(), name="create"),

    # PDF report — full employee list
    path("report/pdf/", views.EmployeeReportPDFView.as_view(), name="report_pdf"),

    # Employee detail
    path("<int:pk>/", views.EmployeeDetailView.as_view(), name="detail"),

    # Edit an employee
    path("<int:pk>/edit/", views.EmployeeUpdateView.as_view(), name="update"),

    # Biometric enrollment
    path("<int:pk>/enroll/", views.EmployeeEnrollView.as_view(), name="enroll"),
    path("<int:pk>/biometric/delete/", views.EmployeeDeleteBiometricView.as_view(), name="biometric_delete"),
]
