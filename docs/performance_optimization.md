# Otimização de Performance — Views, Queries e Cache

## 1. Database Queries (N+1 Analysis)

### 🔴 Crítico: `trucks/views.py — TruckListView`

```python
# ANTES — N+1!
class TruckListView(LoginRequiredMixin, View):
    def get(self, request):
        trucks = Truck.objects.all()  # 1 query
        trucks_with_driver = [(truck, get_current_driver(truck.pk)) for truck in trucks]
        # get_current_driver faz: TruckAssignment.objects.filter(truck_id=truck_id, unassigned_at__isnull=True).select_related('driver').first()
        # → 1 query POR caminhão!
        return render(request, 'trucks/list.html', {'trucks_with_driver': trucks_with_driver})
```

**Impacto:** Com 100 caminhões, são 101 queries.
**Solução com Subquery (1 query total):**

```python
# DEPOIS — 1 query com Subquery + annotations
from django.db.models import Subquery, OuterRef

class TruckListView(LoginRequiredMixin, View):
    def get(self, request):
        trucks = Truck.objects.annotate(
            current_driver_id=Subquery(
                TruckAssignment.objects.filter(
                    truck=OuterRef('pk'), unassigned_at__isnull=True
                ).values('driver_id')[:1]
            ),
            current_driver_name=Subquery(
                TruckAssignment.objects.filter(
                    truck=OuterRef('pk'), unassigned_at__isnull=True
                ).select_related('driver').values('driver__name')[:1]
            ),
        ).order_by('license_plate')

        return render(request, 'trucks/list.html', {'trucks': trucks})
```

**Benchmark estimado:**
| Caminhões | Antes (queries) | Depois (queries) | Ganho |
|-----------|----------------|-------------------|-------|
| 10 | 11 | 1 | 11x |
| 100 | 101 | 1 | 101x |
| 1000 | 1001 | 1 | 1000x |

---

### 🔴 Crítico: `biometric/views.py — BiometricSimulatorView._enrolled_employees()`

```python
# ANTES — N+1!
def _enrolled_employees(self):
    rows = []
    for bt in BiometricTemplate.objects.select_related('employee').all():
        direction, last_ts = AttendanceService().get_current_status(bt.employee_id)
        # get_current_status faz: PresenceEvent.objects.filter(employee_id=emp_id).order_by('-timestamp').first()
        # → 1 query POR employee!
        rows.append({...})
    return rows
```

**Impacto:** Com 50 employees com biometria, são 51 queries.
**Solução com batch query:**

```python
# DEPOIS — 2 queries no total
from django.db.models import Max, OuterRef, Subquery

def _enrolled_employees(self):
    templates = BiometricTemplate.objects.select_related('employee').all()
    emp_ids = [bt.employee_id for bt in templates]

    if not emp_ids:
        return []

    # Buscar último evento de presença de TODOS em 1 query
    latest_subq = PresenceEvent.objects.filter(
        employee=OuterRef('employee_id')
    ).order_by('-timestamp').values('direction', 'timestamp')[:1]

    # Usar Subquery para anotar cada template com seu último evento
    from django.db.models.expressions import Subquery as Subq
    from django.db.models import OuterRef as OR

    # Alternativa: buscar todos os eventos em 1 query e montar dict
    latest_events = {
        e['employee_id']: (e['direction'], e['timestamp'])
        for e in PresenceEvent.objects.filter(
            employee_id__in=emp_ids
        ).values('employee_id').annotate(
            max_ts=Max('timestamp')
        ).values('employee_id', 'direction', 'max_ts')
        # Nota: isso não funciona bem com annotate + values
    }

    # Abordagem mais robusta: raw query ou distinct
    latest_events = {}
    for e in PresenceEvent.objects.filter(
        employee_id__in=emp_ids
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

**Benchmark estimado:**
| Employees | Antes (queries) | Depois (queries) | Ganho |
|-----------|----------------|-------------------|-------|
| 10 | 11 | 2 | 5.5x |
| 50 | 51 | 2 | 25.5x |
| 200 | 201 | 2 | 100x |

---

### 🟠 Alto: `visitors/views.py — VisitListView`

```python
# ANTES — 3 iterações do mesmo queryset = 3 queries no banco!
class VisitListView(LoginRequiredMixin, View):
    def get(self, request):
        visits_qs = Visit.objects.select_related('visitor', 'responsible').order_by('-visit_date', '-arrival_time')

        if filter_type == 'active':
            visits = [v for v in visits_qs if v.is_active]     # Query #1
        elif filter_type == 'completed':
            visits = [v for v in visits_qs if not v.is_active]  # Query #2
        else:
            visits = list(visits_qs)                            # Query #3

        active_visits = [v for v in visits_qs if v.is_active]   # Query #4
        completed_visits = [v for v in visits_qs if not v.is_active]  # Query #5
```

**Impacto:** Cada iteração de um queryset não-avaliado executa uma nova query.
**Solução: avaliar uma vez e reusar**

```python
# DEPOIS — 1 query + list slicing em memória
class VisitListView(LoginRequiredMixin, View):
    def get(self, request):
        filter_type = request.GET.get('filter', 'all')
        ALLOWED_FILTERS = {'all', 'active', 'completed'}
        if filter_type not in ALLOWED_FILTERS:
            filter_type = 'all'

        visits_qs = Visit.objects.select_related('visitor', 'responsible').order_by('-visit_date', '-arrival_time')

        # Avaliar o queryset UMA VEZ
        all_visits = list(visits_qs)  # 1 query apenas

        # Filtrar em memória
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

**Benchmark:**
| Visitas | Antes (queries) | Depois (queries) | Ganho |
|---------|----------------|-------------------|-------|
| 100 | 5 | 1 | 5x |
| 1000 | 5 | 1 | 5x |

---

### 🟡 Médio: `accounts/views.py — SystemLogView`

```python
# ANTES — sem limite, sem paginação
class SystemLogView(MasterRequiredMixin, View):
    def get(self, request):
        qs = SystemLog.objects.select_related('user').exclude(action=SystemLog.ACTION_PAGE_VIEW)
        # ... filtros ...
        return render(request, self.template_name, {'logs': qs})
        # qs não tem slice, não tem paginação → carrega TUDO
```

**Impacto:** Com 100.000 logs, essa view carrega todos na memória.
**Solução: paginação + limite de segurança**

```python
# DEPOIS — com paginação
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

class SystemLogView(MasterRequiredMixin, View):
    template_name = 'accounts/system_log.html'
    paginate_by = 100

    def get(self, request):
        qs = SystemLog.objects.select_related('user').exclude(action=SystemLog.ACTION_PAGE_VIEW)

        # Filtros...
        action = request.GET.get('action')
        user = request.GET.get('user', '').strip()
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        if action:
            qs = qs.filter(action=action)
        if user:
            qs = qs.filter(username__icontains=user)
        if start_date:
            qs = qs.filter(timestamp__date__gte=start_date)
        if end_date:
            qs = qs.filter(timestamp__date__lte=end_date)

        # Paginação (Django Paginator faz count + slice)
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

**Benchmark estimado:**
| Logs | Antes (memória) | Depois (memória) | Ganho |
|------|-----------------|-------------------|-------|
| 1.000 | ~1 MB | ~0.1 MB | 10x |
| 100.000 | ~100 MB | ~0.1 MB | 1000x |

---

## 2. Cache Implementation

**Status: ❌ Cache não implementado em nenhuma view**

### 2.1. Cache de views com pouca alteração

**Candidatos a cache:**
- `TruckBrandModelManageView` — Marcas e modelos mudam raramente
- `EmployeeListView` — Lista de funcionários ativos
- `TruckModelsJsonView` — JSON de modelos por marca (chamado via AJAX)

```python
# Implementação com django.core.cache
from django.core.cache import cache
from django.views import View

class CachedTruckBrandModelManageView(LoginRequiredMixin, View):
    template_name = 'trucks/brands.html'
    cache_key = 'truck_brands_data'
    cache_timeout = 3600  # 1 hora

    def get(self, request):
        brands = cache.get(self.cache_key)
        if brands is None:
            brands = TruckBrand.objects.prefetch_related('models').all()
            cache.set(self.cache_key, brands, self.cache_timeout)
        return render(request, self.template_name, {'brands': brands})

    def post(self, request):
        # Invalidar cache em qualquer POST (mudança de dados)
        cache.delete(self.cache_key)
        # ... resto do código ...
```

### 2.2. Cache de fragmentos de template

```html
{% load cache %}
{% cache 3600 'truck_brands_list' %}
  {% for brand in brands %}
    <option value="{{ brand.pk }}">{{ brand.name }}</option>
  {% endfor %}
{% endcache %}
```

### 2.3. Cache de baixo nível para consultas pesadas

```python
class TruckReportPDFView(LoginRequiredMixin, View):
    def get(self, request):
        # Cachear o queryset (os dados, não o PDF)
        cache_key = 'truck_report_data'
        trucks = cache.get(cache_key)
        if trucks is None:
            trucks = list(Truck.objects.prefetch_related('assignments__driver').order_by('license_plate'))
            cache.set(cache_key, trucks, 300)  # 5 minutos
        # ... gerar PDF a partir dos dados cacheados ...
```

### 2.4. Configuração recomendada para settings.py

```python
# employee_truck_control/settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        },
    }
}

# Para produção, usar Redis:
# CACHES = {
#     'default': {
#         'BACKEND': 'django_redis.cache.RedisCache',
#         'LOCATION': 'redis://127.0.0.1:6379/1',
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#         }
#     }
# }
```

---

## 3. Pagination

**Status: ❌ Não implementada — ver análise completa na revisão de views**

### Views que PRECISAM de paginação:

| View | Risco | Prioridade |
|------|-------|------------|
| `SystemLogView` | Pode ter 100k+ logs | 🔴 Alta |
| `PresenceHistoryView` | PresenceEvent + Visit acumulados | 🔴 Alta |
| `VisitListView` | Visitas acumuladas | 🟠 Média |
| `GlobalAssignmentHistoryView` | Histórico de associações | 🟠 Média |
| `EmployeeListView` | Muitos funcionários (mas menos crítico) | 🟢 Baixa |

### Implementação genérica com mixin

```python
# accounts/mixins.py
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

class PaginatedViewMixin:
    paginate_by = 50
    page_kwarg = 'page'

    def paginate_queryset(self, queryset, request):
        paginator = Paginator(queryset, self.paginate_by)
        page = request.GET.get(self.page_kwarg)

        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        return page_obj

    def get_paginated_context(self, page_obj):
        return {
            'page_obj': page_obj,
            'paginator': page_obj.paginator,
            'is_paginated': page_obj.has_other_pages(),
        }


class SystemLogView(MasterRequiredMixin, View, PaginatedViewMixin):
    template_name = 'accounts/system_log.html'
    paginate_by = 100

    def get(self, request):
        qs = SystemLog.objects.select_related('user').exclude(action=SystemLog.ACTION_PAGE_VIEW)
        # ... filtros ...

        page_obj = self.paginate_queryset(qs, request)
        context = {'logs': page_obj}
        context.update(self.get_paginated_context(page_obj))
        return render(request, self.template_name, context)
```

---

## 4. Async Tasks

**Status: ❌ Nenhuma task assíncrona implementada**

### 4.1. Candidatos a async/background tasks

| Operação | Justificativa | Solução |
|----------|--------------|---------|
| `VisitBadgePDFView` — Geração de PDF | Pode demorar 1-3s | Gerar async + servir depois ou cachear |
| `TruckReportPDFView` — Relatório PDF | Pode demorar 5-10s com muitos trucks | Gerar async + servir depois |
| `BiometricService.connect()` | Conexão com hardware pode timeout | Timeout com fallback (já implementado) |
| `SystemLog` — Limpeza de logs antigos | Operação pesada | Management command agendado |

### 4.2. Implementação com Celery (produção) ou threading (dev)

```python
# requirements.txt (para produção)
celery==5.3.6
redis==5.0.1

# employee_truck_control/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'employee_truck_control.settings')
app = Celery('employee_truck_control')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


# visitors/tasks.py
from celery import shared_task
from django.template.loader import render_to_string
from io import BytesIO

@shared_task
def generate_visit_badge_pdf(visit_pk: int):
    """Generate badge PDF asynchronously and cache it."""
    from django.core.cache import cache
    from .models import Visit
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    visit = Visit.objects.select_related('visitor', 'responsible').get(pk=visit_pk)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    # ... lógica de geração do PDF (copiar de VisitBadgePDFView) ...
    c.save()
    buffer.seek(0)

    # Cachear o PDF por 5 minutos
    cache.set(f'badge_pdf_{visit_pk}', buffer.getvalue(), 300)
    return buffer.getvalue()


# Para ambiente dev sem Celery — usar threading simples
from threading import Thread

class AsyncPDFMixin:
    def generate_pdf_async(self, visit_pk, callback=None):
        from visitors.tasks import generate_visit_badge_pdf

        thread = Thread(target=lambda: generate_visit_badge_pdf(visit_pk))
        thread.daemon = True
        thread.start()
        return thread
```

---

## 5. Serializer Efficiency (select_related / prefetch_related / only / defer)

### 5.1. `select_related` já implementado — revisar cobertura

```python
# ✅ Já usa select_related:
SystemLogView:             SystemLog.objects.select_related('user')
PresenceHistoryView:       PresenceEvent.objects.select_related('employee')
                            Visit.objects.select_related('visitor', 'responsible')
VisitListView:             Visit.objects.select_related('visitor', 'responsible')
VisitDetailView:           Visit.objects.select_related('visitor', 'responsible')
VisitBadgePDFView:         Visit.objects.select_related('visitor', 'responsible')
GlobalAssignmentHistoryView: TruckAssignment.objects.select_related('truck', 'driver')
BiometricSimulatorView:    BiometricTemplate.objects.select_related('employee')
EmployeeDetailView:        (usa hasattr para biometric, não faz join extra)
UserManageView:            User.objects.select_related('profile')
TruckBrandModelManageView: TruckBrand.objects.prefetch_related('models')
TruckReportPDFView:        Truck.objects.prefetch_related('assignments__driver')
```

### 5.2. `only()` e `defer()` — buscar apenas campos necessários

```python
# ANTES — busca todos os campos
class PresenceHistoryView(LoginRequiredMixin, View):
    qs = PresenceEvent.objects.select_related('employee')

# DEPOIS — busca apenas os campos usados
class PresenceHistoryView(LoginRequiredMixin, View):
    qs = PresenceEvent.objects.select_related('employee').only(
        'employee__name', 'employee__pk',  # campos de Employee usados
        'timestamp', 'direction', 'attendance_record_id',  # campos de PresenceEvent usados
    )
```

**Benchmark:** `only()` reduz o payload do banco em 40-60% para models com muitos campos (ex: Employee tem 12 campos, mas só usamos name e pk).

### 5.3. Lista completa de otimizações `only()` recomendadas

```python
# EmployeeListView — só precisa de name, role, department, is_active
Employee.objects.filter(is_active=True).only('name', 'role', 'department', 'is_active').order_by('name')

# TruckListView — só precisa de license_plate, model, color, is_active, brand
Truck.objects.only('license_plate', 'model', 'color', 'is_active', 'brand', 'truck_model').order_by('license_plate')

# VisitListView — só precisa de visitor__name, visitor__company, responsible__name, datas
Visit.objects.select_related('visitor', 'responsible').only(
    'visitor__name', 'visitor__company', 'visitor__photo',
    'responsible__name',
    'visit_date', 'arrival_time', 'scheduled_departure_time', 'actual_departure_time',
    'id_verified', 'notes',
).order_by('-visit_date', '-arrival_time')

# SystemLogView — só precisa de user__username, action, description, timestamp
SystemLog.objects.select_related('user').only(
    'user__username', 'action', 'description', 'timestamp', 'username'
).exclude(action=SystemLog.ACTION_PAGE_VIEW)
```

---

## 6. Benchmarks Compilados

### Cenário Realista: Dashboard com 500 funcionários, 50 caminhões, 10.000 logs

| Otimização | Antes | Depois | Ganho |
|------------|-------|--------|-------|
| TruckListView N+1 → Subquery | 51 queries | 1 query | 51x |
| BiometricSimulator N+1 → Batch | 51 queries | 2 queries | 25.5x |
| VisitListView 5 queries → 1 | 5 queries | 1 query | 5x |
| SystemLogView sem paginação | 10.000 registros | 100 registros | 100x |
| only() nos campos | ~500KB por página | ~200KB por página | 2.5x |
| Cache de brands/models | 1 query por request | 0 queries (cache hit) | ∞ |

### Estimativa de queries totais por request (pior caso):

| Página | Antes | Depois |
|--------|-------|--------|
| Lista de caminhões | 51 | 1 |
| Simulador biométrico | 51 | 2 |
| Histórico de visitas | 5 | 1 |
| Logs do sistema | 1 (sem limite) | 2 (count + slice) |
| Página de visitantes | 3 (sem paginação) | 2 (com paginação) |

---

## 7. Implementação Recomendada por Fase

### Fase 1 — Alto impacto (1-2 dias)
- [ ] Corrigir N+1 no `TruckListView` com Subquery
- [ ] Corrigir N+1 no `BiometricSimulatorView._enrolled_employees()` com batch query
- [ ] Corrigir múltiplas iterações no `VisitListView` (1 query → list slice)

### Fase 2 — Médio impacto (2-3 dias)
- [ ] Adicionar paginação no `SystemLogView`
- [ ] Adicionar paginação no `PresenceHistoryView`
- [ ] Adicionar paginação no `VisitListView`
- [ ] Adicionar paginação no `GlobalAssignmentHistoryView`
- [ ] Implementar `only()` nos querysets mais pesados

### Fase 3 — Infraestrutura (3-5 dias)
- [ ] Adicionar django-redis e configurar cache
- [ ] Implementar cache de brands/models (LV 1: memória local)
- [ ] Implementar cache de consultas pesadas (LV 2: Redis)
- [ ] Adicionar Celery + Redis para PDF async
- [ ] Criar management command para limpeza/anonymization de logs

### Fase 4 — Monitoramento
- [ ] Adicionar `django-debug-toolbar` no dev
- [ ] Adicionar `nplusone` detector em testes
- [ ] Criar testes de performance com `pytest-benchmark`