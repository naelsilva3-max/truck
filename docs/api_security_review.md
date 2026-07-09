# Revisão de Segurança — API REST e Aplicação

## Contexto: Projeto sem Django REST Framework

Este projeto **não utiliza Django REST Framework**. É uma aplicação Django tradicional com:
- Class-based views (CBVs) que renderizam templates HTML
- Django Forms para validação de entrada
- Um único endpoint JSON: `TruckModelsJsonView` (retorna modelos por marca)
- Geração de PDF com ReportLab

Esta revisão cobre:
1. Segurança dos endpoints existentes (incluindo o JSON)
2. Recomendações para implementar uma API REST futura com DRF
3. Configuração de CORS, Throttling, Swagger
4. Melhorias de segurança imediatas

---

## 1. Validação de Entrada (Forms / Serializers)

**Status: ⚠️ Boa cobertura via Django Forms, mas com gaps**

### ✅ Forms com validação adequada:

| Form | Validações | Status |
|------|-----------|--------|
| `EmployeeForm` | `clean_name()` (não vazio), `clean_hire_date()` (não futura) | ✅ |
| `TruckForm` | `clean_license_plate()` (uppercase), `clean_chassis()` (uppercase), `clean()` (brand/model match) | ✅ |
| `TruckAssignmentForm` | Queryset filtra `is_driver=True, is_active=True` | ✅ |
| `VisitorForm` | `clean_name()` (duplicidade), `clean_phone()` (duplicidade) | ✅ |
| `VisitForm` | Validação via model `clean()` (scheduled_departure > arrival) | ✅ |

### ❌ Gaps de validação:

#### 🔴 `accounts/views.py — UserCreateView` — Sem form, validação manual frágil

```python
# ANTES — validação manual, sem form, sem validação de senha
class UserCreateView(MasterRequiredMixin, View):
    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', UserProfile.SIMPLE)
        # Sem validação de complexidade de senha!
        # Sem validação de tamanho mínimo de username!
```

**Correção — criar UserCreateForm:**

```python
# accounts/forms.py
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from accounts.models import UserProfile

class UserCreateForm(forms.Form):
    username = forms.CharField(
        max_length=150, min_length=3,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Nome de Usuário',
    )
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Senha',
    )
    role = forms.ChoiceField(
        choices=[(UserProfile.SIMPLE, 'Simples'), (UserProfile.ADMIN, 'Admin'), (UserProfile.MASTER, 'Master')],
        required=False, initial=UserProfile.SIMPLE,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Função',
    )

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password(password)  # Usa validadores do settings.AUTH_PASSWORD_VALIDATORS
        return password

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Nome de usuário já existe.')
        return username
```

#### 🟡 `TruckBrandModelManageView` — Action não validada

```python
# ANTES — action arbitrária do POST
def post(self, request):
    action = request.POST.get('action')
    # action pode ser qualquer string: 'delete_all', 'hack', etc.
    if action == 'add_brand':
        ...
    elif action == 'delete_brand':
        ...
```

**Correção:**

```python
ALLOWED_ACTIONS = {'add_brand', 'add_model', 'delete_brand', 'delete_model'}

def post(self, request):
    action = request.POST.get('action')
    if action not in ALLOWED_ACTIONS:
        messages.error(request, 'Ação inválida.')
        return redirect('trucks:brands')
    # ...
```

#### 🟡 `Employee.phone` e `Visitor.phone` — Sem validação de formato

```python
# employees/forms.py — Adicionar validação
from django.core.validators import RegexValidator

class EmployeeForm(forms.ModelForm):
    phone = forms.CharField(
        required=False,
        validators=[RegexValidator(
            r'^[\d\s\(\)\+\-]{8,20}$',
            'Formato de telefone inválido. Use apenas números, espaços, parênteses, + e -.'
        )],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(99) 99999-9999'}),
    )
```

---

## 2. Permission Classes

**Status: ⚠️ Parcial — inconsistências graves (já documentado na revisão de views)**

### Resumo do problema:

| App | Views de escrita | Proteção atual | Risco |
|-----|-----------------|----------------|-------|
| `accounts/` | UserCreateView, UserToggleActiveView, UserChangeRoleView | `MasterRequiredMixin` | ✅ |
| `employees/` | EmployeeCreateView, EmployeeUpdateView, EmployeeEnrollView | `EditRequiredMixin` | ✅ |
| `trucks/` | TruckCreateView, TruckUpdateView, AssignDriverView, UnassignDriverView, TruckBrandModelManageView | `LoginRequiredMixin` **apenas** | ❌ |
| `visitors/` | VisitorCreateView, VisitorUpdateView, VisitCreateView, VisitDepartView | `LoginRequiredMixin` **apenas** | ❌ |
| `attendance/` | AttendanceListView (DELETE) | `LoginRequiredMixin` **apenas** | ❌ |

### Correção imediata:

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

## 3. Rate Limiting / Throttling

**Status: ❌ Não implementado**

### 3.1. Implementação com django-ratelimit (sem DRF)

```python
# requirements.txt
django-ratelimit==4.1.0
```

```python
# accounts/mixins.py — RateLimitMixin reutilizável
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

class RateLimitMixin:
    """Apply rate limiting to POST requests of any view."""
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


class UserCreateView(MasterRequiredMixin, RateLimitMixin, View):
    rate_limit_rate = '5/h'  # 5 criações de usuário por hora

    def post(self, request):
        was_limited = getattr(request, 'limited', False)
        if was_limited:
            messages.error(request, 'Muitas tentativas. Aguarde 1 hora.')
            return render(request, self.template_name, {'action': 'Criar'})
        # ... resto do código
```

### 3.2. Taxas recomendadas por endpoint:

| View | Método | Taxa | Justificativa |
|------|--------|------|---------------|
| `UserCreateView` | POST | `5/h` | Criação de usuário — brute-force |
| `UserToggleActiveView` | POST | `10/m` | Toggle de status |
| `UserChangeRoleView` | POST | `10/m` | Mudança de role |
| `EmployeeEnrollView` | POST | `5/m` | Captura biométrica |
| `AssignDriverView` | POST | `10/m` | Associação de motorista |
| `VisitDepartView` | POST | `10/m` | Registro de saída |
| `VisitCreateView` | POST | `20/m` | Criação de visita |
| `TruckBrandModelManageView` | POST | `10/m` | CRUD de marcas/modelos |
| `BiometricSimulatorView` | POST | `5/m` | Simulação (só DEBUG) |

---

## 4. CORS Configuration

**Status: ✅ Não necessário atualmente (sem API REST), mas preparar para futuro**

### 4.1. Configuração atual

O projeto não tem endpoints de API consumidos por frontend separado (SPA). Tudo é server-side rendering com Django templates. **CORS não é necessário.**

### 4.2. Preparação para futuro (quando adicionar DRF)

```python
# requirements.txt
django-cors-headers==4.3.1
```

```python
# employee_truck_control/settings.py
INSTALLED_APPS = [
    ...
    'corsheaders',
    'rest_framework',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Deve vir antes de CommonMiddleware
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    ...
]

# CORS — produção
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'https://meudominio.com https://app.meudominio.com',
).split()

# CORS — desenvolvimento
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
CORS_ALLOW_HEADERS = [
    'accept', 'authorization', 'content-type', 'x-csrftoken',
    'x-requested-with',
]
```

---

## 5. Swagger / API Documentation

**Status: ❌ Não implementado (não há API REST para documentar)**

### 5.1. Preparação para DRF + Swagger

Quando implementar DRF, adicionar:

```python
# requirements.txt
djangorestframework==3.15.1
drf-spectacular==0.27.2
```

```python
# employee_truck_control/settings.py
INSTALLED_APPS = [
    ...
    'rest_framework',
    'drf_spectacular',
]

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Employee Truck Control API',
    'DESCRIPTION': 'API para controle de funcionários, caminhões, biometria e visitas',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
```

```python
# employee_truck_control/urls.py
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    ...
    # API docs (apenas em DEBUG)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

### 5.2. Documentação do endpoint JSON existente

O endpoint `TruckModelsJsonView` já existe e retorna JSON. Documentar:

```python
class TruckModelsJsonView(LoginRequiredMixin, View):
    """
    Return JSON list of models for a given brand — used by the form JS.
    
    **Endpoint:** GET /trucks/models/<brand_pk>/json/
    
    **Response:**
    ```json
    [
        {"pk": 1, "name": "FH 460"},
        {"pk": 2, "name": "R 440"}
    ]
    ```
    
    **Authentication:** Required (LoginRequiredMixin)
    **Permissions:** Any authenticated user
    """
    def get(self, request, brand_pk):
        models = TruckModel.objects.filter(brand_id=brand_pk).values('pk', 'name')
        return JsonResponse(list(models), safe=False)
```

---

## 6. Error Handling

**Status: ⚠️ Parcial — gaps importantes**

### 6.1. Views sem try/except

```python
# accounts/views.py — UserCreateView
# ANTES — sem tratamento de erro
user = User.objects.create_user(username=username, password=password)
profile, _ = UserProfile.objects.get_or_create(user=user)
profile.role = role
profile.save()
# Se IntegrityError → 500 Internal Server Error
```

**Correção:**

```python
# DEPOIS — com tratamento
from django.db import IntegrityError

class UserCreateView(MasterRequiredMixin, View):
    def post(self, request):
        # ... validação ...
        try:
            user = User.objects.create_user(username=username, password=password)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save(update_fields=['role'])
        except IntegrityError:
            messages.error(request, 'Erro de concorrência: usuário já foi criado.')
            return render(request, self.template_name, {'action': 'Criar'})
        except Exception as exc:
            log_action(request, SystemLog.ACTION_ERROR, f'Erro ao criar usuário: {exc}')
            messages.error(request, 'Erro interno ao criar usuário.')
            return render(request, self.template_name, {'action': 'Criar'})
        # ... sucesso ...
```

### 6.2. Views que precisam de tratamento:

| View | Risco | Exceção possível |
|------|-------|-----------------|
| `UserCreateView.post()` | 🔴 | IntegrityError, ValidationError |
| `UserToggleActiveView.post()` | 🟠 | DatabaseError |
| `UserChangeRoleView.post()` | 🟠 | DatabaseError |
| `AssignDriverView.post()` | 🟠 | IntegrityError (unique constraint) |
| `VisitDepartView.post()` | 🟡 | DatabaseError |

### 6.3. Middleware de erro global (500 handler)

```python
# employee_truck_control/views.py
from django.http import HttpResponseServerError
from django.template import loader

def handler500(request, exception=None):
    """Custom 500 error handler that logs and shows friendly message."""
    import logging
    logger = logging.getLogger('django')
    logger.error(f'500 error on {request.path}', exc_info=exception)
    
    template = loader.get_template('500.html')
    return HttpResponseServerError(template.render({'request': request}))
```

```python
# employee_truck_control/urls.py
handler500 = 'employee_truck_control.views.handler500'
```

---

## 7. Segurança do Endpoint JSON Existente

### 7.1. `TruckModelsJsonView` — Análise

```python
class TruckModelsJsonView(LoginRequiredMixin, View):
    def get(self, request, brand_pk):
        models = TruckModel.objects.filter(brand_id=brand_pk).values('pk', 'name')
        return JsonResponse(list(models), safe=False)
```

**Riscos identificados:**

| Risco | Severidade | Descrição |
|-------|-----------|-----------|
| `brand_pk` não validado | 🟡 Médio | Se não for inteiro, filter(brand_id=brand_pk) pode retornar vazio ou erro |
| Sem rate limiting | 🟡 Médio | Pode ser chamado muitas vezes via JS |
| Dados expostos | 🟢 Baixo | Apenas pk e name, sem dados sensíveis |

**Correção:**

```python
class TruckModelsJsonView(LoginRequiredMixin, View):
    def get(self, request, brand_pk):
        try:
            brand_pk = int(brand_pk)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'ID da marca inválido.'}, status=400)
        
        models = TruckModel.objects.filter(brand_id=brand_pk).values('pk', 'name')
        return JsonResponse(list(models), safe=False)
```

---

## 8. Headers de Segurança

**Status: ✅ Bem configurado no settings.py**

```python
# ✅ Já implementado:
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
```

### 🟡 Sugestão adicional — Content Security Policy:

```python
# employee_truck_control/settings.py
MIDDLEWARE = [
    'csp.middleware.CSPMiddleware',  # django-csp
    ...
]

CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:", "blob:")
CSP_FONT_SRC = ("'self'", "https://cdn.jsdelivr.net")
```

---

## 9. Proteção de Dados Sensíveis (LGPD)

**Status: ⚠️ Parcial — gaps importantes**

### 🔴 `BiometricTemplate.template` sem criptografia

```python
# employees/models.py
template = models.BinaryField(
    verbose_name='Template',
    help_text='Dados binários do template biométrico (máx. 10 KB).',
)
```

**Solução:** Criptografar com Fernet (detalhes no `docs/models_review.md`).

### 🟡 `Employee.document_photo` e `Visitor.document_photo` sem proteção de acesso

```python
# employees/models.py
document_photo = models.ImageField(upload_to='employees/documents/')
```

**Solução:** Servir arquivos via view protegida:

```python
# employees/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404

class ProtectedDocumentView(LoginRequiredMixin, View):
    """Serve document photos only to authenticated users with proper permissions."""
    
    def get(self, request, model_name, pk):
        if model_name == 'employee':
            from .models import Employee
            obj = get_object_or_404(Employee, pk=pk)
        elif model_name == 'visitor':
            from visitors.models import Visitor
            obj = get_object_or_404(Visitor, pk=pk)
        else:
            raise Http404
        
        if not obj.document_photo:
            raise Http404
        
        # Verificar permissão: apenas admin/master ou o próprio
        if not request.user.profile.can_edit():
            raise Http404
        
        return FileResponse(obj.document_photo.open(), content_type='image/jpeg')
```

```python
# employee_truck_control/urls.py
urlpatterns = [
    ...
    path('documents/<str:model_name>/<int:pk>/', ProtectedDocumentView.as_view(), name='protected_document'),
]
```

### 🟢 `SystemLog.ip_address` — Anonimização

```python
# Management command: anonymize_old_ips.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Value
from django.db.models.fields import GenericIPAddressField

class Command(BaseCommand):
    help = 'Anonymize IP addresses in SystemLog older than N days'
    
    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90)
    
    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        updated = SystemLog.objects.filter(
            timestamp__lt=cutoff, ip_address__isnull=False
        ).update(
            ip_address=Value(None, output_field=GenericIPAddressField())
        )
        self.stdout.write(f'Anonymized {updated} IP addresses.')
```

---

## 10. Checklist de Implementação — API REST Futura

Quando decidir implementar uma API REST com Django REST Framework:

### Fase 1 — Setup (1 dia)
- [ ] `pip install djangorestframework drf-spectacular django-cors-headers django-ratelimit`
- [ ] Adicionar `rest_framework`, `drf_spectacular`, `corsheaders` ao `INSTALLED_APPS`
- [ ] Configurar `REST_FRAMEWORK` no settings.py (permissions, auth, throttling, pagination)
- [ ] Configurar `SPECTACULAR_SETTINGS` para Swagger
- [ ] Configurar `CORS_ALLOWED_ORIGINS`

### Fase 2 — Serializers (2 dias)
- [ ] `accounts/serializers.py` — UserSerializer, UserProfileSerializer, SystemLogSerializer
- [ ] `employees/serializers.py` — EmployeeSerializer, BiometricTemplateSerializer
- [ ] `trucks/serializers.py` — TruckSerializer, TruckAssignmentSerializer, TruckBrandSerializer, TruckModelSerializer
- [ ] `visitors/serializers.py` — VisitorSerializer, VisitSerializer
- [ ] `attendance/serializers.py` — AttendanceRecordSerializer, PresenceEventSerializer

### Fase 3 — ViewSets (2 dias)
- [ ] `accounts/views_api.py` — UserViewSet, UserProfileViewSet, SystemLogViewSet
- [ ] `employees/views_api.py` — EmployeeViewSet, BiometricTemplateViewSet
- [ ] `trucks/views_api.py` — TruckViewSet, TruckAssignmentViewSet, TruckBrandViewSet, TruckModelViewSet
- [ ] `visitors/views_api.py` — VisitorViewSet, VisitViewSet
- [ ] `attendance/views_api.py` — AttendanceRecordViewSet, PresenceEventViewSet

### Fase 4 — Segurança (1 dia)
- [ ] `DEFAULT_PERMISSION_CLASSES: IsAuthenticated`
- [ ] Throttle rates por ViewSet
- [ ] Testes de permissão para cada endpoint
- [ ] Swagger UI protegido (apenas admin)

### Fase 5 — Documentação (1 dia)
- [ ] Schema OpenAPI com drf-spectacular
- [ ] Swagger UI em `/api/docs/`
- [ ] Redoc em `/api/redoc/`

---

## 11. Resumo das Prioridades

| Prioridade | Ação | Impacto |
|------------|------|---------|
| 🔴 Crítica | Criar `UserCreateForm` com validação de senha | Senhas fracas, username sem validação |
| 🔴 Crítica | Adicionar `EditRequiredMixin` em `trucks/` e `visitors/` | Qualquer user logado cria/edita dados |
| 🔴 Crítica | Criptografar `BiometricTemplate.template` | Dados biométricos expostos (LGPD) |
| 🟠 Alta | Adicionar rate limiting nas views POST | Vulnerável a brute-force |
| 🟠 Alta | Proteger `document_photo` com view autenticada | Documentos sensíveis expostos |
| 🟠 Alta | Validar `action` no `TruckBrandModelManageView` | Ação arbitrária via POST |
| 🟡 Média | Adicionar try/except nas views de `accounts/` | 500 errors sem tratamento |
| 🟡 Média | Validar `brand_pk` como inteiro no `TruckModelsJsonView` | Bad request sem validação |
| 🟡 Média | Adicionar `phone` validators nos forms | Dados inconsistentes |
| 🟢 Baixa | Adicionar CSP headers | Proteção XSS adicional |
| 🟢 Baixa | Anonimizar IPs antigos no SystemLog | LGPD — direito ao esquecimento |
| 🟢 Baixa | Custom 500 handler | Melhor UX em erros |