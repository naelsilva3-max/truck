# Revisão de Segurança e Performance — Views

## 1. Rate Limiting

**Status: ❌ Não implementado em nenhuma view**

Nenhuma view utiliza `django-ratelimit` ou `django-throttle-requests`. Views de criação de usuário (`UserCreateView`), login implícito, e endpoints POST estão totalmente expostos a brute-force e abuso.

### Sugestão de implementação

Adicione `django-ratelimit` ao `requirements.txt` e aplique decorators:

```python
# requirements.txt
django-ratelimit==4.1.0
```

```python
# accounts/views.py
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

class UserCreateView(MasterRequiredMixin, View):
    template_name = 'accounts/user_form.html'

    @method_decorator(ratelimit(key='ip', rate='5/h', method='POST'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        was_limited = getattr(request, 'limited', False)
        if was_limited:
            messages.error(request, 'Muitas tentativas. Aguarde 1 hora.')
            return render(request, self.template_name, {'action': 'Criar'})
        # ... resto do código
```

Ou crie um mixin reutilizável:

```python
# accounts/mixins.py
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

class RateLimitMixin:
    rate_limit_key = 'ip'
    rate_limit_rate = '10/m'
    rate_limit_method = 'POST'

    @method_decorator(ratelimit(
        key=lambda self: self.rate_limit_key,
        rate=lambda self: self.rate_limit_rate,
        method=lambda self: self.rate_limit_method,
        block=False,
    ))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
```

---

## 2. Permission Classes

**Status: ⚠️ Parcialmente implementado — inconsistências graves**

### Problemas encontrados

| View | Mixin | Problema |
|------|-------|----------|
| `accounts/views.py` — todas | `MasterRequiredMixin` | ✅ Correto |
| `attendance/views.py` — todas | `LoginRequiredMixin` apenas | ❌ Qualquer usuário logado vê presença de qualquer funcionário |
| `biometric/views.py` | `LoginRequiredMixin` apenas | ❌ Qualquer usuário logado pode simular biometria |
| `employees/views.py` — `EmployeeCreateView`, `EmployeeUpdateView`, `EmployeeEnrollView` | `EditRequiredMixin` | ✅ Correto |
| `employees/views.py` — `EmployeeListView`, `EmployeeDetailView` | `LoginRequiredMixin` apenas | ⚠️ Aceitável para leitura, mas sem role check |
| `trucks/views.py` — todas | `LoginRequiredMixin` apenas | ❌ Qualquer usuário logado pode criar/editar caminhões e associar motoristas |
| `visitors/views.py` — todas | `LoginRequiredMixin` apenas | ❌ Qualquer usuário logado pode criar/editar visitantes e visitas |

### Sugestão de correção

Views de escrita (POST/PUT/DELETE) em `trucks/`, `visitors/` e `attendance/` devem usar `EditRequiredMixin`:

```python
# trucks/views.py
from accounts.mixins import EditRequiredMixin

class TruckCreateView(EditRequiredMixin, View):  # Antes: LoginRequiredMixin
    ...

class TruckUpdateView(EditRequiredMixin, View):
    ...

class AssignDriverView(EditRequiredMixin, View):
    ...

class UnassignDriverView(EditRequiredMixin, View):
    ...

class TruckBrandModelManageView(EditRequiredMixin, View):
    ...
```

```python
# visitors/views.py
from accounts.mixins import EditRequiredMixin

class VisitorCreateView(EditRequiredMixin, View):
    ...

class VisitorUpdateView(EditRequiredMixin, View):
    ...

class VisitCreateView(EditRequiredMixin, View):
    ...

class VisitDepartView(EditRequiredMixin, View):
    ...
```

---

## 3. Validação de Entrada

**Status: ⚠️ Parcialmente implementado — falhas críticas**

### Problemas encontrados

1. **`accounts/views.py` — `UserCreateView.post()`** (linha 18-19): Validação manual frágil. Não usa Django Forms. Não valida complexidade de senha.

2. **`trucks/views.py` — `TruckBrandModelManageView.post()`** (linha 54): `action` vem do POST sem validação de valor permitido. Um atacante pode enviar `action=delete_all` ou qualquer string arbitrária.

3. **`biometric/views.py` — `BiometricSimulatorView.post()`** (linha 52): `employee_pk` não é validado como inteiro antes da query.

4. **`attendance/views.py` — `PresenceHistoryView.get()`** (linha 57): `employee_pk` não validado como inteiro.

5. **`visitors/views.py` — `VisitListView.get()`** (linha 81): `filter_type` não validado contra lista de valores permitidos.

### Sugestões de correção

```python
# accounts/views.py — Usar Django Form
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

class UserCreateForm(forms.Form):
    username = forms.CharField(max_length=150, min_length=3)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=[
        (UserProfile.SIMPLE, 'Simples'),
        (UserProfile.ADMIN, 'Admin'),
        (UserProfile.MASTER, 'Master'),
    ], required=False, initial=UserProfile.SIMPLE)

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password(password)  # Usa validadores do settings.AUTH_PASSWORD_VALIDATORS
        return password

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise ValidationError('Nome de usuário já existe.')
        return username
```

```python
# trucks/views.py — Validar action
ALLOWED_ACTIONS = {'add_brand', 'add_model', 'delete_brand', 'delete_model'}

def post(self, request):
    action = request.POST.get('action')
    if action not in ALLOWED_ACTIONS:
        messages.error(request, 'Ação inválida.')
        return redirect('trucks:brands')
    # ...
```

```python
# attendance/views.py — Validar employee_pk como inteiro
def get(self, request):
    employee_pk = request.GET.get('employee')
    if employee_pk:
        try:
            employee_pk = int(employee_pk)
        except (ValueError, TypeError):
            employee_pk = None
    # ...
```

```python
# visitors/views.py — Validar filter_type
ALLOWED_FILTERS = {'all', 'active', 'completed'}

def get(self, request):
    filter_type = request.GET.get('filter', 'all')
    if filter_type not in ALLOWED_FILTERS:
        filter_type = 'all'
    # ...
```

---

## 4. N+1 Queries (select_related / prefetch_related)

**Status: ⚠️ Vários problemas de N+1 identificados**

### Problemas encontrados

1. **`trucks/views.py` — `TruckListView.get()`** (linha 96-97)
```python
trucks = Truck.objects.all()  # ❌ Sem select_related
trucks_with_driver = [(truck, get_current_driver(truck.pk)) for truck in trucks]
# get_current_driver faz 1 query por caminhão → N+1!
```

2. **`trucks/views.py` — `TruckReportPDFView.get()`** (linha 303-318)
```python
trucks = Truck.objects.prefetch_related('assignments__driver').order_by('license_plate')
# ❌ assignments__driver é um prefetch aninhado, mas acessar a.driver.name dentro do loop
# pode causar queries adicionais se o prefetch não funcionar corretamente
```

3. **`visitors/views.py` — `VisitListView.get()`** (linha 83-93)
```python
visits_qs = Visit.objects.select_related('visitor', 'responsible').order_by(...)
# ❌ Itera 3 vezes sobre o mesmo queryset (visits, active_visits, completed_visits)
# Cada iteração executa a query novamente!
```

4. **`biometric/views.py` — `_enrolled_employees()`** (linha 32-41)
```python
for bt in BiometricTemplate.objects.select_related('employee').all():
    direction, last_ts = AttendanceService().get_current_status(bt.employee_id)
    # ❌ get_current_status faz query em PresenceEvent → 1 query por employee
```

5. **`employees/views.py` — `EmployeeDetailView.get_context_data()`** (linha 77)
```python
svc = AttendanceService()
direction, last_ts = svc.get_current_status(self.object.pk)
# ❌ 1 query extra por detail view (aceitável para detail, mas mencionar)
```

### Sugestões de correção

```python
# trucks/views.py — Resolver N+1 no TruckListView
from django.db.models import Prefetch

class TruckListView(LoginRequiredMixin, View):
    def get(self, request):
        # Buscar todos os trucks com assignment ativo em 1 query
        trucks = Truck.objects.annotate(
            current_driver_name=Subquery(
                TruckAssignment.objects.filter(
                    truck=OuterRef('pk'), unassigned_at__isnull=True
                ).select_related('driver').values('driver__name')[:1]
            ),
            current_driver_id=Subquery(
                TruckAssignment.objects.filter(
                    truck=OuterRef('pk'), unassigned_at__isnull=True
                ).values('driver_id')[:1]
            ),
        ).order_by('license_plate')
        return render(request, 'trucks/list.html', {'trucks': trucks})
```

```python
# visitors/views.py — Evitar múltiplas iterações do queryset
class VisitListView(LoginRequiredMixin, View):
    template_name = 'visitors/visit_list.html'

    def get(self, request):
        filter_type = request.GET.get('filter', 'all')
        if filter_type not in {'all', 'active', 'completed'}:
            filter_type = 'all'

        visits_qs = Visit.objects.select_related('visitor', 'responsible').order_by('-visit_date', '-arrival_time')

        # Avaliar o queryset UMA VEZ
        all_visits = list(visits_qs)

        active_visits = [v for v in all_visits if v.is_active]
        completed_visits = [v for v in all_visits if not v.is_active]

        if filter_type == 'active':
            visits = active_visits
        elif filter_type == 'completed':
            visits = completed_visits
        else:
            visits = all_visits

        return render(request, self.template_name, {
            'visits': visits,
            'active_visits': active_visits,
            'completed_visits': completed_visits,
            'filter_type': filter_type,
            'active_count': len(active_visits),
            'completed_count': len(completed_visits),
        })
```

```python
# biometric/views.py — Otimizar N+1 com batch query
def _enrolled_employees(self):
    """Return employees that have a BiometricTemplate, with a display code."""
    templates = BiometricTemplate.objects.select_related('employee').all()
    employee_ids = [bt.employee_id for bt in templates]

    # Buscar status de TODOS os employees em 1 query
    from django.db.models import Max, Case, When, Value, CharField
    from attendance.models import PresenceEvent

    latest_events = {
        e.employee_id: (e.direction, e.timestamp)
        for e in PresenceEvent.objects.filter(
            employee_id__in=employee_ids
        ).values('employee_id').annotate(
            max_ts=Max('timestamp')
        ).select_related('employee')  # Isso não funciona com values, ajustar
    }
    # Alternativa mais simples:
    latest_events = {}
    for e in PresenceEvent.objects.filter(
        employee_id__in=employee_ids
    ).order_by('employee_id', '-timestamp').distinct('employee_id'):
        latest_events[e.employee_id] = (e.direction, e.timestamp)

    rows = []
    for bt in templates:
        direction, last_ts = latest_events.get(bt.employee_id, (None, None))
        code = hashlib.sha256(bytes(bt.template)).hexdigest()[:12].upper()
        rows.append({
            'employee': bt.employee,
            'code': code,
            'direction': direction,
            'last_ts': last_ts,
            'is_in': direction == PresenceEvent.IN,
        })
    rows.sort(key=lambda r: r['employee'].name)
    return rows
```

---

## 5. Pagination

**Status: ❌ Não implementada em nenhuma view**

Views que listam muitos registros sem paginação:

- `accounts/views.py` — `SystemLogView` (pode ter milhares de logs)
- `attendance/views.py` — `PresenceHistoryView` (eventos de presença + visitas)
- `visitors/views.py` — `VisitListView` (visitas acumuladas)
- `trucks/views.py` — `GlobalAssignmentHistoryView` (histórico de associações)
- `trucks/views.py` — `TruckReportPDFView` (relatório PDF, mas aceitável)

### Sugestão de implementação

```python
# accounts/views.py
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

class SystemLogView(MasterRequiredMixin, View):
    template_name = 'accounts/system_log.html'
    paginate_by = 50

    def get(self, request):
        qs = SystemLog.objects.select_related('user').exclude(action=SystemLog.ACTION_PAGE_VIEW)

        # ... filtros ...

        paginator = Paginator(qs, self.paginate_by)
        page = request.GET.get('page')

        try:
            logs = paginator.page(page)
        except PageNotAnInteger:
            logs = paginator.page(1)
        except EmptyPage:
            logs = paginator.page(paginator.num_pages)

        return render(request, self.template_name, {'logs': logs})
```

```python
# attendance/views.py — Paginação no PresenceHistoryView
from django.core.paginator import Paginator

class PresenceHistoryView(LoginRequiredMixin, View):
    template_name = 'attendance/presence_history.html'
    paginate_by = 100

    def get(self, request):
        # ... montagem da lista de events ...

        events.sort(key=lambda e: e['timestamp'], reverse=True)

        paginator = Paginator(events, self.paginate_by)
        page = request.GET.get('page')
        try:
            events_page = paginator.page(page)
        except PageNotAnInteger:
            events_page = paginator.page(1)
        except EmptyPage:
            events_page = paginator.page(paginator.num_pages)

        return render(request, self.template_name, {
            'events': events_page,
            # ... resto do contexto ...
        })
```

---

## 6. Exception Handling

**Status: ⚠️ Parcialmente implementado — gaps importantes**

### Problemas encontrados

1. **`accounts/views.py` — `UserCreateView.post()`** (linha 33-36): Sem try/except. Se `create_user` ou `get_or_create` falhar (ex: IntegrityError raro), o usuário vê um 500.

2. **`accounts/views.py` — `UserToggleActiveView.post()`** (linha 56-57): Sem try/except. `target.save()` pode falhar.

3. **`accounts/views.py` — `UserChangeRoleView.post()`** (linha 70-73): Sem try/except. `get_or_create` e `save()` podem falhar.

4. **`trucks/views.py` — `AssignDriverView.post()`** (linha 164-175): Captura `Exception` genérico (muito amplo), mas `assignment.save()` pode lançar `IntegrityError` específico.

5. **`visitors/views.py` — `VisitDepartView.post()`** (linha 155): `update()` não levanta exceções de validação, mas se o banco falhar, não há tratamento.

6. **`biometric/views.py` — `BiometricSimulatorView.post()`** (linha 57-63): Captura `BiometricTemplate.DoesNotExist`, mas se houver outro erro de banco, será 500.

### Sugestões de correção

```python
# accounts/views.py — Adicionar try/except
from django.db import IntegrityError

class UserCreateView(MasterRequiredMixin, View):
    def post(self, request):
        # ... validação ...

        try:
            user = User.objects.create_user(username=username, password=password)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save()
        except IntegrityError:
            messages.error(request, 'Erro de concorrência: usuário já foi criado por outro administrador.')
            return render(request, self.template_name, {'action': 'Criar'})
        except Exception as exc:
            log_action(request, SystemLog.ACTION_ERROR, f'Erro ao criar usuário: {exc}')
            messages.error(request, 'Erro interno ao criar usuário. Tente novamente.')
            return render(request, self.template_name, {'action': 'Criar'})

        log_action(request, SystemLog.ACTION_CREATE, f'Usuário criado: {username} (role={role})')
        messages.success(request, f'Usuário "{username}" criado com sucesso.')
        return redirect('accounts:manage_users')
```

```python
# accounts/views.py — ToggleActive com tratamento
class UserToggleActiveView(MasterRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, 'Você não pode desativar sua própria conta.')
            return redirect('accounts:manage_users')

        try:
            target.is_active = not target.is_active
            target.save(update_fields=['is_active'])  # Mais eficiente
        except Exception as exc:
            log_action(request, SystemLog.ACTION_ERROR, f'Erro ao alterar status de {target.username}: {exc}')
            messages.error(request, 'Erro interno ao alterar status do usuário.')
            return redirect('accounts:manage_users')

        state = 'reativado' if target.is_active else 'desativado'
        log_action(request, SystemLog.ACTION_UPDATE, f'Usuário {target.username} {"ativado" if target.is_active else "desativado"}')
        messages.success(request, f'Usuário "{target.username}" {state}.')
        return redirect('accounts:manage_users')
```

---

## 7. Problemas Adicionais de Segurança

### 7.1. DEBUG check ausente no BiometricSimulatorView

O comentário no topo do arquivo diz "Only available when DEBUG=True", mas não há verificação real:

```python
# biometric/views.py — Adicionar proteção
from django.conf import settings
from django.http import Http404

class BiometricSimulatorView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404('Simulador disponível apenas em ambiente de desenvolvimento.')
        return super().dispatch(request, *args, **kwargs)
```

### 7.2. CSRF Protection

Todas as views POST usam `request.POST`, o que significa que o CSRF middleware está protegendo. ✅ Verificar se o template inclui `{% csrf_token %}` em todos os formulários.

### 7.3. Logging de ações sensíveis

`accounts/views.py` usa `log_action()` corretamente. ✅ Mas `trucks/views.py` e `visitors/views.py` **não registram ações de criação/edição**:

```python
# trucks/views.py — Adicionar logging
from accounts.logging import log_action
from accounts.models import SystemLog

class TruckCreateView(EditRequiredMixin, View):
    def post(self, request):
        form = TruckForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                truck = form.save()
                log_action(request, SystemLog.ACTION_CREATE, f'Caminhão criado: {truck.license_plate}')
                messages.success(request, f'Caminhão {truck.license_plate} cadastrado com sucesso.')
                return redirect('trucks:detail', pk=truck.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
        # ...
```

### 7.4. Mass Assignment

`TruckBrandModelManageView.post()` usa `get_or_create` com dados do POST sem sanitização. Validar com forms do Django é mais seguro.

---

## 8. Problemas de Performance Adicionais

### 8.1. `SystemLogView` sem limite de resultados

```python
# accounts/views.py — Adicionar limite
class SystemLogView(MasterRequiredMixin, View):
    def get(self, request):
        qs = SystemLog.objects.select_related('user').exclude(action=SystemLog.ACTION_PAGE_VIEW)
        # ... filtros ...
        qs = qs[:500]  # Limite de segurança mesmo sem paginação
        return render(request, self.template_name, {'logs': qs})
```

### 8.2. `update_fields` ausente em saves parciais

```python
# accounts/views.py — Otimizar saves
target.is_active = not target.is_active
target.save(update_fields=['is_active'])  # Evita atualizar todos os campos

# profile.role = role
# profile.save(update_fields=['role'])  # Apenas o campo que mudou
```

### 8.3. `count()` vs `len()` em querysets

```python
# employees/views.py — Usar count() em vez de carregar tudo
ctx['inactive_count'] = Employee.objects.filter(is_active=False).count()  # ✅ Já está correto
```

---

## Resumo das Prioridades

| Prioridade | Categoria | Impacto |
|------------|-----------|---------|
| 🔴 Crítica | Permission classes ausentes em `trucks/`, `visitors/`, `attendance/` | Qualquer usuário logado pode criar/editar dados |
| 🔴 Crítica | N+1 em `TruckListView` | Degradação severa com muitos caminhões |
| 🔴 Crítica | N+1 em `BiometricSimulatorView._enrolled_employees()` | Degradação severa com muitos employees |
| 🟠 Alta | Rate limiting ausente | Vulnerável a brute-force |
| 🟠 Alta | Paginação ausente em `SystemLogView`, `PresenceHistoryView`, `VisitListView` | Páginas podem ficar lentas com muitos dados |
| 🟠 Alta | Validação de entrada frágil em `UserCreateView` | Senhas fracas, username sem validação |
| 🟡 Média | Exception handling ausente em `accounts/views.py` | Usuário vê 500 em vez de mensagem amigável |
| 🟡 Média | Múltiplas iterações do queryset em `VisitListView` | 3x mais queries no banco |
| 🟢 Baixa | `update_fields` ausente | Overhead desnecessário em saves |
| 🟢 Baixa | DEBUG check ausente no simulador biométrico | Risco em produção |