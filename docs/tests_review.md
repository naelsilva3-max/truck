# Revisão de Cobertura de Testes

## Resumo dos Arquivos de Teste

| App | Arquivo | Qtd Testes | Framework | Cobertura |
|-----|---------|------------|-----------|-----------|
| `accounts` | `tests.py` | **0** | unittest | ❌ Vazio (só placeholder) |
| `attendance/tests` | `test_service.py` | **7** | pytest | ✅ Service layer |
| `biometric/tests` | `test_service.py` | **16** | pytest | ✅ Service + exceptions |
| `biometric/tests` | `test_listener.py` | **14** | pytest | ✅ Listener thread |
| `employees/tests` | `test_models.py` | **11** | pytest | ✅ Model validation |
| `trucks/tests` | `test_models.py` | **18** | pytest | ✅ Model + security |
| `trucks/tests` | `test_integration.py` | **9** | pytest | ✅ Integration flows |
| `trucks/tests` | `test_properties.py` | **17** | pytest+hypothesis | ✅ Property-based |
| `visitors` | `tests.py` | **0** | unittest | ❌ Vazio (só placeholder) |

**Total: ~92 testes** — boa base, mas com lacunas críticas.

---

## 1. Cobertura de Testes Críticos

### ✅ Coberto:
- **Employee**: criação, validação de nome, data de admissão, desativação preserva registros
- **BiometricTemplate**: validação de tamanho (0 bytes, >10KB), re-enrollment idempotente
- **Truck**: placa Mercosul/antigo, chassi, ano, unicidade, uppercase, soft delete
- **TruckAssignment**: driver validation, temporal invariants, active assignment constraint
- **AttendanceService**: record_entry, record_exit, process_biometric_event (IN/OUT), date filter
- **BiometricService**: connect/disconnect, capture_template, identify (1:N), min_score
- **BiometricListener**: lifecycle, callback invocation, exception isolation, reconnection
- **Integration**: enrollment flow, biometric toggle, truck assignment flow

### ❌ **Não coberto (lacunas críticas):**

#### 🔴 **accounts/** — Zero testes
```python
# accounts/tests.py — VAZIO
from django.test import TestCase
# Create your tests here.
```
**Faltam testes para:**
- `UserProfile` — criação, role validation, `__str__()`, `can_edit()`, `is_simple/admin/master`
- `UserCreateView` — criação de usuário, username duplicado, senha fraca
- `UserManageView` — listagem com `select_related`
- `UserToggleActiveView` — toggle, auto-desativação bloqueada
- `UserChangeRoleView` — mudança de role
- `SystemLog` — criação, imutabilidade (save/delete), `__str__()`
- `SystemLogView` — filtros (action, user, date), paginação
- `log_action()` — integração com SystemLog
- `context_processors` — se existir
- `signals` — se existir

#### 🔴 **visitors/** — Zero testes
```python
# visitors/tests.py — VAZIO
from django.test import TestCase
# Create your tests here.
```
**Faltam testes para:**
- `Visitor` — validação de nome, `__str__()`
- `Visit` — validação de scheduled_departure > arrival, `is_active` property
- `VisitorListView` — listagem, ordenação
- `VisitorCreateView` — POST com dados válidos/inválidos
- `VisitorUpdateView` — edição de visitante
- `VisitListView` — filtro active/completed/all, N+1 (3 iterações do queryset)
- `VisitCreateView` — criação com VisitForm
- `VisitDetailView` — detail com select_related
- `VisitDepartView` — registro de saída, duplicidade
- `VisitBadgePDFView` — geração de PDF, fallback de fonte

#### 🟡 **attendance/** — Testes apenas do service, faltam views
```python
# attendance/tests/test_service.py — SÓ TESTA AttendanceService
```
**Faltam testes para:**
- `AttendanceListView` — GET, DELETE (HttpResponseNotAllowed)
- `PresenceHistoryView` — combinação de PresenceEvent + Visit, filtros type/employee/date

#### 🟡 **employees/** — Testes apenas de models, faltam views
```python
# employees/tests/test_models.py — SÓ TESTA Employee e BiometricTemplate
```
**Faltam testes para:**
- `EmployeeListView` — show_inactive filter, inactive_count
- `EmployeeCreateView` — POST com EmployeeForm, log_action
- `EmployeeDetailView` — has_biometric, presence status
- `EmployeeUpdateView` — edição, log_action
- `EmployeeEnrollView` — GET, POST (com/sem biometria), timeout, erro de dispositivo, template vazio

---

## 2. Uso de Fixtures

**Status: ✅ Nenhuma fixture externa — factories inline (padrão aceitável)**

Todos os testes usam funções helper inline para criar dados:

```python
def make_employee(**kw) -> Employee:
    defaults = dict(name="Test", role="Op", hire_date=date(2020, 1, 1))
    defaults.update(kw)
    return Employee.objects.create(**defaults)
```

### Sugestão: Criar conftest.py com fixtures compartilhadas

```python
# conftest.py (na raiz do projeto)
import pytest
from datetime import date
from django.contrib.auth.models import User
from employees.models import Employee
from trucks.models import Truck

@pytest.fixture
def admin_user(db):
    return User.objects.create_user(username="admin", password="pass", is_staff=True)

@pytest.fixture
def simple_user(db):
    return User.objects.create_user(username="user", password="pass")

@pytest.fixture
def employee(db):
    return Employee.objects.create(
        name="João Silva", role="Operador", hire_date=date(2020, 1, 1)
    )

@pytest.fixture
def driver(db):
    return Employee.objects.create(
        name="Motorista", role="Driver", hire_date=date(2020, 1, 1), is_driver=True
    )

@pytest.fixture
def truck(db):
    return Truck.objects.create(
        license_plate="ABC1D23", model="Volvo FH",
        color="Branco", chassis="12345678901234567", year=2020,
    )

@pytest.fixture
def client_logged_admin(client, admin_user):
    client.login(username="admin", password="pass")
    return client

@pytest.fixture
def client_logged_user(client, simple_user):
    client.login(username="user", password="pass")
    return client
```

---

## 3. Mocks em Chamadas Externas

**Status: ✅ Mock bem implementado nas views com dependências externas**

### ✅ BiometricService mockado corretamente:

```python
# employees/views.py — mock do BiometricService
mock_service = MagicMock()
mock_service.connect.return_value = True
mock_service.capture_template.return_value = dummy_template
mock_service.is_connected = True

with patch("employees.views.BiometricService", return_value=mock_service):
    response = client.post(f"/employees/{emp.pk}/enroll/")
```

### ✅ AttendanceService mockado corretamente:

```python
# attendance/tests/test_service.py
mock_bio = MagicMock()
mock_bio.identify.return_value = emp.pk
svc = AttendanceService(biometric_service=mock_bio)
```

### ✅ BiometricListener com mock service:

```python
# biometric/tests/test_listener.py — _MockService
class _MockService:
    """A minimal BiometricService-shaped object for controlling test scenarios."""
```

### ❌ **ReportLab NÃO mockado** — `VisitBadgePDFView` e `TruckReportPDFView`

```python
# visitors/views.py — VisitBadgePDFView
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as canvas_module
```

**Sugestão:** Para testar views que geram PDF, verificar o content-type sem precisar validar o conteúdo binário:

```python
def test_badge_pdf_generation(client_logged_admin, visit):
    response = client_logged_admin.get(f"/visitors/{visit.pk}/badge/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline; filename=")
```

---

## 4. Testes de Permissão/Autenticação

**Status: ✅ Parcial — testado no `trucks/tests/test_models.py` mas faltam na maioria das apps**

### ✅ Testes existentes:

```python
# trucks/tests/test_models.py — TestSecurityConstraints
def test_unauthenticated_employee_list_redirects(self):
    client = Client()
    response = client.get("/employees/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]

def test_unauthenticated_truck_list_redirects(self):
    client = Client()
    response = client.get("/trucks/")
    assert response.status_code == 302

def test_unauthenticated_attendance_redirects(self):
    client = Client()
    response = client.get(f"/employees/{emp.pk}/attendance/")
    assert response.status_code == 302
```

### ❌ **Testes faltando (autenticação):**

```python
# Para CADA view, testar:
def test_view_redirects_unauthenticated(client):
    response = client.get("/caminho/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]
```

**Views sem teste de autenticação:**
- `/accounts/users/new/` — `UserCreateView`
- `/accounts/users/` — `UserManageView`
- `/accounts/users/<pk>/toggle/` — `UserToggleActiveView`
- `/accounts/users/<pk>/role/` — `UserChangeRoleView`
- `/accounts/logs/` — `SystemLogView`
- `/biometric/simulator/` — `BiometricSimulatorView`
- `/attendance/presence-history/` — `PresenceHistoryView`
- `/trucks/brands/` — `TruckBrandModelManageView`
- `/trucks/<pk>/` — `TruckDetailView`
- `/trucks/<pk>/assign/` — `AssignDriverView`
- `/trucks/<pk>/unassign/` — `UnassignDriverView`
- `/trucks/<pk>/assignments/` — `AssignmentHistoryView`
- `/trucks/assignments/` — `GlobalAssignmentHistoryView`
- `/trucks/report/pdf/` — `TruckReportPDFView`
- `/trucks/models/<brand_pk>/json/` — `TruckModelsJsonView`
- `/visitors/` — `VisitorListView`
- `/visitors/new/` — `VisitorCreateView`
- `/visitors/<pk>/edit/` — `VisitorUpdateView`
- `/visits/` — `VisitListView`
- `/visits/new/` — `VisitCreateView`
- `/visits/<pk>/` — `VisitDetailView`
- `/visits/<pk>/depart/` — `VisitDepartView`
- `/visits/<pk>/badge/` — `VisitBadgePDFView`

### ❌ **Testes faltando (permissão por role):**

Com base na revisão de views, `trucks/`, `visitors/` e `attendance/` usam apenas `LoginRequiredMixin`. Mas mesmo onde `EditRequiredMixin`/`MasterRequiredMixin` existem, não há testes:

```python
def test_simple_user_cannot_create_employee(client_logged_user):
    response = client_logged_user.post("/employees/new/", {
        "name": "Test", "role": "Op", "hire_date": "2022-01-01",
    })
    # Deve redirecionar ou retornar 403
    assert response.status_code in (302, 403)
    # Verificar mensagem de erro
    messages = list(response.context["messages"])
    assert any("permissão" in str(m).lower() for m in messages)

def test_master_user_can_manage_users(client_logged_admin):
    response = client_logged_admin.get("/accounts/users/")
    assert response.status_code == 200
```

---

## 5. Testes de Validação

**Status: ✅ Bem implementado em models — faltam testes de formulários**

### ✅ Testes de validação existentes:

| Model | Validação testada |
|-------|------------------|
| `Employee` | Nome vazio, whitespace-only, data futura |
| `BiometricTemplate` | 0 bytes, >10KB, re-enroll |
| `Truck` | Placa inválida, chassi curto/inválido, ano <1900, ano futuro, unicidade placa/chassi |
| `TruckAssignment` | Non-driver, unassigned_at < assigned_at, soft delete |
| `AttendanceRecord` | (via property tests) exit_time > entry_time |
| `AttendanceService` | Exit sem open record, unknown fingerprint |

### ❌ **Testes de formulários faltando:**

```python
# Testar forms diretamente
from employees.forms import EmployeeForm
from trucks.forms import TruckForm, TruckAssignmentForm
from visitors.forms import VisitorForm, VisitForm

def test_employee_form_valid_data():
    form = EmployeeForm(data={
        "name": "João", "role": "Op", "hire_date": "2022-01-01",
        "is_driver": False, "is_active": True,
    })
    assert form.is_valid()

def test_employee_form_invalid_blank_name():
    form = EmployeeForm(data={"name": "", "role": "Op", "hire_date": "2022-01-01"})
    assert not form.is_valid()
    assert "name" in form.errors

def test_truck_form_invalid_plate():
    form = TruckForm(data={
        "license_plate": "INVALID",
        "color": "Branco",
        "chassis": "12345678901234567",
        "year": 2020,
    })
    assert not form.is_valid()
    assert "license_plate" in form.errors

def test_truck_assignment_form_non_driver():
    employee = make_employee(is_driver=False)
    form = TruckAssignmentForm(data={"driver": employee.pk})
    assert not form.is_valid()
```

### ❌ **Testes de validação de view faltando:**

```python
# Testar validação via HTTP POST
def test_create_employee_with_blank_name_returns_form_errors(client_logged_admin):
    response = client_logged_admin.post("/employees/new/", {
        "name": "", "role": "Op", "hire_date": "2022-01-01",
    })
    assert response.status_code == 200  # Renderiza o form novamente
    assert "name" in response.context["form"].errors

def test_create_employee_with_future_hire_date_is_rejected(client_logged_admin):
    from datetime import date, timedelta
    future = date.today() + timedelta(days=1)
    response = client_logged_admin.post("/employees/new/", {
        "name": "Test", "role": "Op", "hire_date": future.isoformat(),
    })
    assert response.status_code == 200
    assert "hire_date" in response.context["form"].errors
```

---

## 6. Lacunas Adicionais

### 6.1. Testes de propriedade Hypothesis

✅ Já existem 17 testes de propriedade em `trucks/tests/test_properties.py` — excelente!

**Sugestão de novos property tests:**

```python
# Property: UserProfile role consistency
@given(role=st.sampled_from(['simple', 'admin', 'master']))
def test_userprofile_role_consistency(role):
    user = User.objects.create_user(username=f"u{unique_suffix()}", password="pass")
    profile = UserProfile.objects.create(user=user, role=role)
    assert profile.is_simple == (role == 'simple')
    assert profile.is_admin == (role == 'admin')
    assert profile.is_master == (role == 'master')
    assert profile.can_edit() == (role in ('admin', 'master'))

# Property: Visit temporal invariants
@given(
    arrival=st.times(),
    departure=st.times(),
)
def test_visit_scheduled_departure_after_arrival(arrival, departure):
    assume(departure > arrival)
    visitor = Visitor.objects.create(name="Test")
    responsible = Employee.objects.create(name="Resp", role="Mgr", hire_date=date(2020, 1, 1))
    visit = Visit(
        visitor=visitor, responsible=responsible,
        visit_date=date.today(),
        arrival_time=arrival,
        scheduled_departure_time=departure,
    )
    visit.full_clean()  # não deve levantar ValidationError
```

### 6.2. Testes de Edge Cases

```python
# SystemLog imutabilidade
def test_systemlog_cannot_be_deleted():
    log = SystemLog.objects.create(username="admin", action="create", description="test")
    with pytest.raises(PermissionError):
        log.delete()
    assert SystemLog.objects.filter(pk=log.pk).exists()

def test_systemlog_cannot_be_modified():
    log = SystemLog.objects.create(username="admin", action="create", description="test")
    with pytest.raises(PermissionError):
        log.description = "modified"
        log.save()

# BiometricSimulatorView DEBUG check
def test_simulator_404_when_debug_false(client_logged_admin, settings):
    settings.DEBUG = False
    response = client_logged_admin.get("/biometric/simulator/")
    assert response.status_code == 404

# PresenceEvent imutabilidade
def test_presence_event_cannot_be_deleted():
    emp = make_employee()
    event = PresenceEvent.objects.create(
        employee=emp, direction=PresenceEvent.IN, timestamp=timezone.now()
    )
    with pytest.raises(PermissionError):
        event.delete()
```

### 6.3. Testes de URL Conf

```python
# Testar que todas as URLs resolvem
from django.urls import reverse

def test_accounts_urls_resolve():
    assert reverse("accounts:manage_users")
    assert reverse("accounts:system_logs")
    # ...

def test_employees_urls_resolve():
    assert reverse("employees:list")
    assert reverse("employees:create")
    # ...
```

---

## Resumo das Prioridades

| Prioridade | O que testar | Impacto |
|------------|-------------|---------|
| 🔴 Crítica | `accounts/tests.py` — zero testes | UserProfile, SystemLog, todas as views de accounts sem cobertura |
| 🔴 Crítica | `visitors/tests.py` — zero testes | Visitor, Visit, todas as views de visitors sem cobertura |
| 🟠 Alta | Views de `attendance/` sem teste | AttendanceListView, PresenceHistoryView |
| 🟠 Alta | Views de `employees/` sem teste (fora enrollment) | ListView, CreateView, DetailView, UpdateView |
| 🟠 Alta | Testes de permissão por role ausentes | Ninguém testa se `simple` user consegue criar/edit |
| 🟡 Média | Forms sem teste direto | EmployeeForm, TruckForm, TruckAssignmentForm, VisitorForm, VisitForm |
| 🟡 Média | PDF views sem teste | VisitBadgePDFView, TruckReportPDFView |
| 🟡 Média | `BiometricSimulatorView` sem teste | Só a view de simulação não tem testes |
| 🟢 Baixa | conftest.py com fixtures compartilhadas | Reduz duplicação nos testes |
| 🟢 Baixa | Property tests para UserProfile e Visit | Expande cobertura baseada em Hypothesis |

---

## Checklist de Implementação Recomendada

### Fase 1 — Crítico (preencher lacunas de apps inteiras)

- [ ] `accounts/tests/test_models.py` — UserProfile validation, SystemLog immutability
- [ ] `accounts/tests/test_views.py` — UserCreateView, UserManageView, UserToggleActiveView, UserChangeRoleView, SystemLogView
- [ ] `visitors/tests/test_models.py` — Visitor validation, Visit validation, is_active property
- [ ] `visitors/tests/test_views.py` — VisitorListView, VisitorCreateView, VisitorUpdateView, VisitListView, VisitCreateView, VisitDetailView, VisitDepartView, VisitBadgePDFView

### Fase 2 — Alto (cobrir views e permissões)

- [ ] `attendance/tests/test_views.py` — AttendanceListView, PresenceHistoryView
- [ ] `employees/tests/test_views.py` — EmployeeListView, EmployeeCreateView, EmployeeDetailView, EmployeeUpdateView, EmployeeEnrollView
- [ ] Testes de permissão: `simple` user bloqueado de CREATE/UPDATE/DELETE em todos os apps
- [ ] Testes de autenticação: todas as views redirecionam quando não logado

### Fase 3 — Melhoria contínua

- [ ] `conftest.py` com fixtures compartilhadas
- [ ] Testes de forms: EmployeeForm, TruckForm, TruckAssignmentForm, VisitorForm, VisitForm
- [ ] Property tests: UserProfile, Visit
- [ ] Testes de BiometricSimulatorView (DEBUG check)
- [ ] Testes de PDF (apenas verificar Content-Type)