# Implementation Plan: Employee & Truck Control

## Overview

System web desenvolvido em Python/Django para controle de ponto de funcionários via biometria digital (leitor ZKTeco ZK9500) e gestão de frota de caminhões da empresa. O plano de implementação cobre quatro módulos principais — `employees`, `trucks`, `attendance` e `biometric` — além de testes unitários, testes baseados em propriedades, testes de integração e um comando de gerenciamento para o listener biométrico em background.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "tasks": ["1"],
      "description": "Project setup and base configuration — foundation for all other tasks"
    },
    {
      "wave": 1,
      "tasks": ["2"],
      "description": "Employee and BiometricTemplate models — required by all other modules"
    },
    {
      "wave": 2,
      "tasks": ["3", "4", "6"],
      "description": "Employee forms/views, BiometricService layer, and Truck models — independent of each other, all depend on wave 1"
    },
    {
      "wave": 3,
      "tasks": ["5", "7"],
      "description": "Attendance module (depends on Employee model + BiometricService) and Truck forms/views (depends on Truck models + Employee)"
    },
    {
      "wave": 4,
      "tasks": ["8"],
      "description": "Security and access control — requires all views from waves 2-3 to exist"
    },
    {
      "wave": 5,
      "tasks": ["9", "10", "11", "12"],
      "description": "Unit tests, property-based tests, integration tests, and management command — all depend on completed implementation from waves 1-4"
    }
  ]
}
```

## Tasks

- [x] 1. Project Setup and Base Configuration
  - [x] 1.1 Initialize Django project structure with apps `employees`, `trucks`, `attendance`, and `biometric`
    - Create Django project `employee_truck_control` and the four apps
    - Configure `settings.py` with installed apps, database (SQLite default, PostgreSQL-ready), static files, and login redirect URL
    - Add `requirements.txt` with pinned versions: Django>=4.2, pyzkfp, Pillow>=10.0, pytest-django>=4.0, hypothesis>=6.0, whitenoise>=6.0, psycopg2-binary>=2.9
    - Configure `pytest.ini` / `pyproject.toml` for `pytest-django` with `DJANGO_SETTINGS_MODULE`
    - Set up base URL routing in `urls.py` pointing to each app's `urls.py`
  - [x] 1.2 Create base templates and static assets structure
    - Create `templates/base.html` with navigation, login/logout links, and Django messages block
    - Create `templates/registration/login.html` for Django auth login page
    - Configure `whitenoise` middleware for static file serving
    - Add Bootstrap or minimal CSS via static files

- [x] 2. Employee Module — Models
  - [x] 2.1 Implement `Employee` model
    - Define `Employee` model with fields: `name` (CharField 200), `role` (CharField 100), `department` (CharField 100, blank), `phone` (CharField 20, blank), `hire_date` (DateField), `is_driver` (BooleanField default False), `is_active` (BooleanField default True), `created_at`, `updated_at`
    - Add `clean()` validation: `name` must not be blank/whitespace-only; `hire_date` must not be in the future
    - Override `save()` to call `full_clean()` so model-level validation is enforced on ORM saves
    - Register in Django Admin
  - [x] 2.2 Implement `BiometricTemplate` model
    - Define `BiometricTemplate` with fields: `employee` (OneToOneField → Employee, CASCADE, related_name='biometric'), `template` (BinaryField), `finger_index` (SmallIntegerField default 0), `enrolled_at` (auto_now_add), `updated_at` (auto_now)
    - Add `clean()` validation: `template` bytes length must be > 0 and ≤ 10,240 (10 KB)
    - Ensure the model is NOT accessible via any URL or API serializer — access restricted at view layer
    - Register in Django Admin (read-only display, no template bytes exposed)
  - [x] 2.3 Generate and apply migrations for `employees` app

- [x] 3. Employee Module — Forms and Views
  - [x] 3.1 Implement `EmployeeForm` (ModelForm)
    - Include all editable fields with appropriate widgets and help texts
    - Validate `name` (not blank/whitespace), `hire_date` (not future) in `clean_*` methods
    - Return field-level error messages matching requirements 1.2 and 1.3
  - [x] 3.2 Implement CRUD views for Employee
    - `EmployeeListView` — lists all employees; decorated with `@login_required`
    - `EmployeeCreateView` — renders `EmployeeForm`, saves on POST, redirects to enroll page on success; `@login_required`
    - `EmployeeDetailView` — shows employee data and biometric status; `@login_required`; returns HTTP 404 if not found
    - `EmployeeUpdateView` — pre-fills `EmployeeForm`, saves on POST; `@login_required`; returns HTTP 404 if not found
    - `EmployeeDeleteView` — shows confirmation dialog with employee name and biometric info (if present); on confirm POST, deletes employee and associated `BiometricTemplate`; on cancel, preserves data; `@login_required`
    - Wire all views to `employees/urls.py` and include in main `urls.py`
  - [x] 3.3 Create Employee templates
    - `employees/list.html` — table of employees with name, role, department, is_driver status, is_active badge, and action links
    - `employees/form.html` — create/edit form with field validation error display
    - `employees/detail.html` — employee detail with biometric status badge and enrollment link
    - `employees/confirm_delete.html` — confirmation dialog showing employee name and biometric template info

- [x] 4. Biometric Module — Service Layer
  - [x] 4.1 Implement `BiometricService` class
    - Create `biometric/service.py` with class `BiometricService`
    - Implement `connect(device_id=None, host=None, port=None) -> bool`: attempts connection to ZKTeco ZK9500 via pyzkfp; raises `BiometricDeviceNotFoundError` if device not found; returns `True` on success
    - Implement `disconnect() -> None`: safely releases hardware resources; no-op if already disconnected
    - Implement `capture_template() -> bytes`: captures fingerprint template from connected device; raises error if not connected
    - Implement `identify(template: bytes, templates: list[tuple[int, bytes]]) -> int | None`: performs 1:N comparison using pyzkfp scoring with configurable minimum score threshold; returns `employee_id` of best match or `None` if below threshold
    - Define custom exception `BiometricDeviceNotFoundError` in `biometric/exceptions.py`
  - [x] 4.2 Implement `BiometricListener`
    - Create `BiometricListener` class in `biometric/listener.py`
    - Implement `start_listener(callback: Callable[[bytes], None]) -> None`: registers callback before starting monitoring thread; runs in `threading.Thread`; does not block the Django server
    - Implement `stop_listener() -> None`: signals the background thread to stop gracefully
    - Add exception handling inside the listener loop: catch all exceptions per event, log with full stack trace via Python `logging`, and continue processing subsequent events (requirement 4.4)
    - Add reconnection logic: if ZKTeco ZK9500 becomes unavailable, log the hardware error and retry connection without terminating the listener (requirement 3.10)
  - [x] 4.3 Implement biometric enrollment view
    - Create `EmployeeEnrollView` at `POST /employees/<id>/enroll/`
    - On GET: render enrollment start page with instructions
    - On POST: call `BiometricService.capture_template()`; if success, upsert `BiometricTemplate` (create or replace existing); display success message
    - If `BiometricDeviceNotFoundError` or capture timeout: display user-friendly error message; do NOT persist any template (requirement 2.7)
    - If captured template is 0 bytes or > 10 KB: display error message; do NOT persist (requirement 2.3)
    - Decorate with `@login_required`

- [ ] 5. Attendance Module — Models, Service, and Views
  - [x] 5.1 Implement `AttendanceRecord` model
    - Define `AttendanceRecord` with fields: `employee` (ForeignKey → Employee, PROTECT, related_name='attendance_records'), `entry_time` (DateTimeField), `exit_time` (DateTimeField null/blank), `date` (DateField), `created_at` (auto_now_add)
    - Add `Meta`: `ordering = ['-entry_time']`; indexes on `['employee', 'date']` and `['employee', 'exit_time']`
    - Add `clean()` validation: if `exit_time` is set, it must be at least 1 second after `entry_time` (requirement 3.6)
    - Override `save()` to auto-populate `date` from `entry_time` and call `full_clean()`
    - Block physical deletion at model level: override `delete()` to raise `PermissionError` (requirement 11.1)
  - [x] 5.2 Implement `AttendanceService`
    - Create `attendance/service.py` with class `AttendanceService`
    - Implement `get_open_record(employee_id: int) -> AttendanceRecord | None`: returns open record (exit_time=None) for the employee
    - Implement `record_entry(employee_id: int) -> AttendanceRecord`: creates new record with `entry_time=now`, `date=today`
    - Implement `record_exit(employee_id: int) -> AttendanceRecord`: finds open record and sets `exit_time=now`; validates exit > entry by at least 1 second
    - Implement `process_biometric_event(template: bytes) -> AttendanceRecord`: calls `BiometricService.identify()`; if None, logs "digital desconhecida" and returns None; otherwise calls `record_entry` or `record_exit` based on toggle logic (requirements 3.3, 3.4, 3.5)
    - Implement `list_records(employee_id: int, start_date=None, end_date=None) -> QuerySet`: returns records ordered by `-entry_time`; filters by `date` range when provided
  - [x] 5.3 Implement Attendance views
    - `AttendanceListView` at `GET /employees/<id>/attendance/`: lists all attendance records for the employee; supports optional `start_date`/`end_date` query params; `@login_required`; 404 if employee not found
    - Wire to `attendance/urls.py` and include in main `urls.py`
  - [x] 5.4 Create Attendance templates
    - `attendance/list.html` — table with `entry_time`, `exit_time` (blank if null), and `date` per record (requirement 8.4); date filter form at top
  - [x] 5.5 Generate and apply migrations for `attendance` app

- [x] 6. Truck Module — Models
  - [x] 6.1 Implement `Truck` model
    - Define `Truck` with fields: `license_plate` (CharField 10, unique), `model` (CharField 100), `color` (CharField 50), `chassis` (CharField 50, unique), `year` (IntegerField null/blank), `is_active` (BooleanField default True), `created_at`, `updated_at`
    - Add `clean()` validation:
      - `license_plate`: must match regex for Mercosul (`^[A-Z]{3}[0-9][A-Z][0-9]{2}$`) OR old Brazilian format (`^[A-Z]{3}[0-9]{4}$`); normalized to uppercase
      - `chassis`: must be exactly 17 alphanumeric characters (requirement 6.6)
      - `year`: if set, must be between 1900 and current year inclusive (requirement 6.1)
      - `model` and `color` must not be blank (requirement 6.2)
    - Override `save()` to call `full_clean()` and normalize `license_plate` to uppercase
    - Block physical deletion: override `delete()` to raise `PermissionError`; use `is_active=False` for soft-delete (requirement 11.3)
    - Register in Django Admin
  - [x] 6.2 Implement `TruckAssignment` model
    - Define `TruckAssignment` with fields: `truck` (ForeignKey → Truck, PROTECT, related_name='assignments'), `driver` (ForeignKey → Employee, PROTECT, related_name='truck_assignments'), `assigned_at` (DateTimeField default timezone.now), `unassigned_at` (DateTimeField null/blank), `notes` (TextField blank)
    - Add `Meta`: `ordering = ['-assigned_at']`
    - Add `clean()` validation:
      - `driver.is_driver` must be True (requirement 7.1)
      - If `unassigned_at` is set, it must be ≥ `assigned_at` (requirement 7.6)
    - Override `save()` to call `full_clean()` and enforce that no other active assignment exists for the same truck before creating a new active one (requirements 7.2, 7.5)
    - Block physical deletion: override `delete()` to raise `PermissionError` (requirement 11.2)
    - Register in Django Admin
  - [x] 6.3 Generate and apply migrations for `trucks` app

- [x] 7. Truck Module — Forms and Views
  - [x] 7.1 Implement `TruckForm` and `TruckAssignmentForm`
    - `TruckForm` (ModelForm): fields `license_plate`, `model`, `color`, `chassis`, `year`, `is_active`; normalize plate to uppercase; return field-level error messages for duplicates, invalid formats
    - `TruckAssignmentForm` (ModelForm): fields `driver` (queryset filtered to `is_driver=True, is_active=True`), `assigned_at`, `notes`; validate no active assignment exists for truck before saving
  - [x] 7.2 Implement CRUD views for Truck
    - `TruckListView` — lists all trucks; `@login_required`
    - `TruckCreateView` — `TruckForm`; `@login_required`
    - `TruckDetailView` — shows truck details, current driver, and assignment history; `@login_required`; 404 if not found
    - `TruckUpdateView` — updates `model`, `color`, `year`, `is_active`; revalidates uniqueness if plate/chassis changed; `@login_required`; 404 if not found
    - Wire to `trucks/urls.py` and include in main `urls.py`
  - [x] 7.3 Implement TruckAssignment views
    - `AssignDriverView` at `POST /trucks/<id>/assign/`: validates driver is_driver=True and no active assignment exists; creates `TruckAssignment` with `assigned_at=now`, `unassigned_at=None`; `@login_required`
    - `UnassignDriverView` at `POST /trucks/<id>/unassign/`: finds active assignment and sets `unassigned_at=now`; returns error if no active assignment or already inactive (requirement 7.9); `@login_required`
    - `AssignmentHistoryView` at `GET /trucks/<id>/assignments/`: returns all assignments ordered by `-assigned_at` (requirement 7.8); `@login_required`
  - [x] 7.4 Implement `TruckManager` methods
    - `get_current_driver(truck_id: int) -> Employee | None`: returns driver of active TruckAssignment or None (requirement 7.7)
    - `list_assignments(truck_id: int) -> QuerySet`: returns all assignments ordered by `-assigned_at`
  - [x] 7.5 Create Truck templates
    - `trucks/list.html` — table with plate, model, color, is_active status, current driver, and action links
    - `trucks/form.html` — create/edit form with field validation errors
    - `trucks/detail.html` — truck details, current driver badge, assign/unassign buttons, assignment history table
    - `trucks/assignments.html` — full assignment history with assigned_at, unassigned_at, driver name, notes

- [x] 8. Security and Access Control
  - [x] 8.1 Apply `@login_required` globally and configure auth URLs
  - [x] 8.2 Protect `BiometricTemplate` data
  - [x] 8.3 Implement soft-delete enforcement

- [x] 9. Unit Tests
  - [x] 9.1 Write unit tests for `Employee` model validation
  - [x] 9.2 Write unit tests for `BiometricTemplate` model validation
  - [x] 9.3 Write unit tests for `AttendanceService` logic
  - [x] 9.4 Write unit tests for `Truck` model validation
  - [x] 9.5 Write unit tests for `TruckAssignment` validation and `TruckManager`
  - [x] 9.6 Write unit tests for security constraints

- [x] 10. Property-Based Tests
  - [x] 10.1 Write property test for Property 1: Employee creation round-trip
  - [x] 10.2 Write property test for Property 2: Invalid employee inputs are rejected
  - [x] 10.3 Write property test for Property 3: Deactivation preserves linked records
  - [x] 10.4 Write property test for Property 4: Biometric enroll is idempotent (OneToOne upsert)
  - [x] 10.5 Write property test for Property 5: Biometric 1:N identification correctness
  - [x] 10.6 Write property test for Property 6: Attendance toggle is mutually exclusive
  - [x] 10.7 Write property test for Property 7: exit_time is always after entry_time
  - [x] 10.8 Write property test for Property 8: BiometricListener resilience to exceptions
  - [x] 10.9 Write property test for Property 9: Truck creation round-trip
  - [x] 10.10 Write property test for Property 10: Unique fields reject duplicates
  - [x] 10.11 Write property test for Property 11: Invalid plate and chassis formats are rejected
  - [x] 10.12 Write property test for Property 12: Only drivers can be assigned to trucks
  - [x] 10.13 Write property test for Property 13: At most one active TruckAssignment per truck
  - [x] 10.14 Write property test for Property 14: TruckAssignment temporal invariant
  - [x] 10.15 Write property test for Property 15: get_current_driver consistency
  - [x] 10.16 Write property test for Property 16: Date filter returns only matching records
  - [x] 10.17 Write property test for Property 17: Soft-delete instead of physical delete

- [x] 11. Integration Tests
  - [x] 11.1 Write integration test: full employee enrollment flow (with BiometricService mock)
  - [x] 11.2 Write integration test: biometric event triggers attendance toggle
  - [x] 11.3 Write integration test: full truck assignment flow

- [x] 12. Management Command: BiometricListener Daemon
  - [x] 12.1 Implement Django management command `start_listener`

## Notes

- The `pyzkfp` library may require manual installation from the ZKTeco SDK if not available via PyPI; `pyzk` is an alternative depending on whether the ZK9500 is accessed via USB HID or TCP/IP protocol. The `BiometricService` should be designed with a backend abstraction to allow swapping between the two.
- All biometric templates are stored as raw bytes in `BinaryField`; they must never be serialized to JSON, rendered in templates, or included in log output (LGPD compliance).
- The `BiometricListener` must run as a `threading.Thread` or as a Django management command daemon — not inside a WSGI worker — to avoid blocking the web server.
- SQLite is the default database for development; for production, switch to PostgreSQL using `psycopg2-binary`. The `AttendanceRecord` indexes (`['employee', 'date']` and `['employee', 'exit_time']`) are important for query performance at scale.
- For 1:N biometric identification with > 500 employees, consider an in-memory cache of templates with `post_save` signal invalidation to avoid loading all templates from the database on every event.
- Soft-delete (`is_active=False`) is the only supported deletion mechanism for `Employee`, `Truck`, `AttendanceRecord`, and `TruckAssignment`. Physical `.delete()` calls on `AttendanceRecord` and `TruckAssignment` must raise `PermissionError`.
- Property-based tests use `hypothesis` with `pytest-django`; run with `pytest --hypothesis-seed=0` for reproducibility in CI.
