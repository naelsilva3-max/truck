"""
URL configuration for the employees app.

Namespace: employees

Routes
------
  /employees/                     → EmployeeListView    (employees:list)
  /employees/new/                 → EmployeeCreateView  (employees:create)
  /employees/<pk>/                → EmployeeDetailView  (employees:detail)
  /employees/<pk>/edit/           → EmployeeUpdateView  (employees:update)
  /employees/<pk>/delete/         → EmployeeDeleteView  (employees:delete)
  /employees/<pk>/enroll/         → placeholder for EmployeeEnrollView (task 4.3)
"""

from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    # List all employees
    path("", views.EmployeeListView.as_view(), name="list"),

    # Create a new employee
    path("new/", views.EmployeeCreateView.as_view(), name="create"),

    # Employee detail
    path("<int:pk>/", views.EmployeeDetailView.as_view(), name="detail"),

    # Edit an employee
    path("<int:pk>/edit/", views.EmployeeUpdateView.as_view(), name="update"),

    # Biometric enrollment — EmployeeEnrollView (task 4.3)
    path("<int:pk>/enroll/", views.EmployeeEnrollView.as_view(), name="enroll"),
]
