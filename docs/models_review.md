# Revisão de Models Django

## 1. Método `__str__()`

**Status: ✅ Todos os models possuem `__str__()`**

| Model | `__str__()` | Observação |
|-------|-------------|------------|
| `UserProfile` | ✅ `f'{self.user.username} ({self.get_role_display()})'` | Correto |
| `SystemLog` | ✅ `f'[{self.timestamp}] {self.username} — {self.get_action_display()}: {self.description}'` | Correto |
| `AttendanceRecord` | ✅ Nome, data, horários | ⚠️ Bug na formatação (ver abaixo) |
| `PresenceEvent` | ✅ `f'{self.employee.name} — {self.direction} — {self.timestamp}'` | Correto |
| `Employee` | ✅ `self.name` | Correto |
| `BiometricTemplate` | ✅ `f'Template biométrico de {self.employee.name}'` | Correto |
| `TruckBrand` | ✅ `self.name` | Correto |
| `TruckModel` | ✅ `f'{self.brand.name} {self.name}'` | Correto |
| `Truck` | ✅ `f'{self.license_plate} — {model_display}'` | Correto |
| `TruckPhoto` | ✅ `f'Foto {self.order} — {self.truck.license_plate}'` | Correto |
| `TruckAssignment` | ✅ `f'{self.truck} ← {self.driver.name} ({status})'` | Correto |
| `Visitor` | ✅ `self.name` | Correto |
| `Visit` | ✅ `f'{self.visitor.name} — {self.visit_date} ({self.arrival_time:%H:%M})'` | Correto |

### 🐛 Bug no `AttendanceRecord.__str__()`

```python
# Linhas 47-52 — OPERADOR TERNÁRIO MAL POSICIONADO
def __str__(self):
    return (
        f'{self.employee.name} — {self.date} '
        f'{self.entry_time:%H:%M} → '
        f'{self.exit_time:%H:%M}' if self.exit_time else
        f'{self.employee.name} — {self.date} {self.entry_time:%H:%M} → em aberto'
    )
```

**Problema:** O `if/else` ternário tem precedência baixa. A expressão é avaliada como:
```python
(f'{self.entry_time:%H:%M} → ' f'{self.exit_time:%H:%M}') if self.exit_time else ...
```
Ou seja, quando `exit_time` é `None`, ele retorna **apenas** o segundo f-string (nome + data + hora + "em aberto") e **descarta** o primeiro f-string. Quando `exit_time` existe, ele retorna **apenas** `self.entry_time → self.exit_time` sem o nome e data.

**Correção:**
```python
def __str__(self):
    if self.exit_time:
        return f'{self.employee.name} — {self.date} {self.entry_time:%H:%M} → {self.exit_time:%H:%M}'
    return f'{self.employee.name} — {self.date} {self.entry_time:%H:%M} → em aberto'
```

---

## 2. Validadores Implementados

**Status: ⚠️ Incompleto — gaps importantes**

### Models com `clean()` e `full_clean()` no `save()`:

| Model | `clean()` | `full_clean()` no `save()` | Observação |
|-------|-----------|---------------------------|------------|
| `UserProfile` | ✅ Valida role | ❌ **Ausente** | `save()` não chama `self.full_clean()` |
| `SystemLog` | ❌ **Ausente** | ❌ **Ausente** (intencional — imutável) | Aceitável |
| `AttendanceRecord` | ✅ Valida exit_time > entry_time | ✅ `self.full_clean()` | Correto |
| `PresenceEvent` | ❌ **Ausente** | ❌ **Ausente** (intencional — imutável) | Aceitável |
| `Employee` | ✅ Valida name, hire_date | ✅ `self.full_clean()` | Correto |
| `BiometricTemplate` | ✅ Valida template (null/empty/tamanho) | ✅ `self.full_clean()` | Correto |
| `TruckBrand` | ❌ **Ausente** | ❌ **Ausente** | Aceitável (só name unique) |
| `TruckModel` | ❌ **Ausente** | ❌ **Ausente** | Aceitável (unique_together já valida) |
| `Truck` | ✅ Valida placa, chassi, ano, brand/model match | ✅ `self.full_clean()` | Correto |
| `TruckPhoto` | ❌ **Ausente** | ❌ **Ausente** | Aceitável |
| `TruckAssignment` | ✅ Valida driver, truck, datas | ❌ **Ausente** | `save()` não chama `self.full_clean()` |
| `Visitor` | ✅ Valida name | ✅ `self.full_clean()` | Correto |
| `Visit` | ✅ Valida scheduled_departure > arrival | ✅ `self.full_clean()` | Correto |

### 🟡 Gaps:

1. **`UserProfile.save()` não chama `full_clean()`**
   ```python
   # accounts/models.py
   def save(self, *args, **kwargs):
       # ❌ self.full_clean() faltando
       super().save(*args, **kwargs)
   ```
   **Correção:**
   ```python
   def save(self, *args, **kwargs):
       self.full_clean()
       super().save(*args, **kwargs)
   ```

2. **`TruckAssignment.save()` não chama `full_clean()`**
   ```python
   # trucks/models.py
   # ❌ save() não foi sobrescrito, então clean() NUNCA é chamado
   ```
   **Correção:**
   ```python
   class TruckAssignment(models.Model):
       # ...
       def save(self, *args, **kwargs):
           self.full_clean()
           super().save(*args, **kwargs)
   ```

### 🟡 Validadores ausentes em campos específicos:

3. **`Employee.phone`** — Sem validação de formato
   ```python
   # Sugestão
   from django.core.validators import RegexValidator
   
   phone = models.CharField(
       max_length=20, blank=True,
       validators=[RegexValidator(r'^[\d\s\(\)\+\-]{8,20}$', 'Formato de telefone inválido.')],
       verbose_name='Telefone',
   )
   ```

4. **`Visitor.phone`** — Mesmo problema
5. **`Visitor.company`** — Sem validação de tamanho mínimo (blank=True, mas poderia ter min_length)
6. **`Truck.year`** — Não tem validação a nível de campo via `validators=[...]`, apenas no `clean()`. Funciona, mas um `MinValueValidator`/`MaxValueValidator` direto no campo seria mais explícito.

---

## 3. Índices de Banco de Dados

**Status: ✅ Bem implementado na maioria dos models**

### Índices existentes:

| Model | Índices | Observação |
|-------|---------|------------|
| `UserProfile` | `user`, `role` | ✅ |
| `SystemLog` | `-timestamp`, `user+action`, `action` | ✅ |
| `AttendanceRecord` | `employee+date`, `employee+exit_time`, `date` | ✅ |
| `PresenceEvent` | `employee+timestamp`, `direction` | ✅ |
| `Employee` | `name`, `is_active`, `department`, `is_driver` | ✅ |
| `BiometricTemplate` | `employee`, `finger_index` | ✅ |
| `TruckBrand` | `name` | ✅ |
| `TruckModel` | `brand+name` | ✅ |
| `Truck` | `license_plate`, `chassis`, `is_active`, `brand+truck_model` | ✅ |
| `TruckPhoto` | `truck+order` | ✅ |
| `TruckAssignment` | `truck+driver`, `assigned_at`, `unassigned_at` | ✅ |
| `Visitor` | `name`, `company` | ✅ |
| `Visit` | `visitor+visit_date`, `responsible`, `visit_date` | ✅ |

### 🟡 Índices sugeridos:

1. **`SystemLog`** — Adicionar índice composto para consultas de filtragem:
   ```python
   models.Index(fields=['action', 'username'], name='idx_systemlog_action_user'),
   models.Index(fields=['-timestamp', 'action'], name='idx_systemlog_ts_action'),
   ```

2. **`AttendanceRecord`** — Índice para busca de registros abertos:
   ```python
   models.Index(fields=['employee', 'exit_time'], name='idx_attendance_emp_exit'),
   # Já existe ✅
   ```

3. **`Visit`** — Índice para filtro de visitas ativas (muito usado em `VisitListView`):
   ```python
   models.Index(fields=['actual_departure_time'], name='idx_visit_departure'),
   ```

---

## 4. Relacionamentos

**Status: ✅ Relacionamentos corretos na maioria — 1 gap de segurança**

### Análise dos relacionamentos:

| Model | FK/O2O | `on_delete` | `related_name` | Correto? |
|-------|--------|-------------|----------------|----------|
| `UserProfile.user` | O2O → `User` | `CASCADE` | `profile` | ✅ |
| `SystemLog.user` | FK → `User` | `PROTECT` | `system_logs` | ✅ (logs preservados) |
| `AttendanceRecord.employee` | FK → `Employee` | `PROTECT` | `attendance_records` | ✅ |
| `PresenceEvent.employee` | FK → `Employee` | `PROTECT` | `presence_events` | ✅ |
| `PresenceEvent.attendance_record` | FK → `AttendanceRecord` | `PROTECT` | `presence_events` | ✅ |
| `BiometricTemplate.employee` | O2O → `Employee` | `CASCADE` | `biometric` | ✅ |
| `TruckModel.brand` | FK → `TruckBrand` | `CASCADE` | `models` | ✅ |
| `Truck.brand` | FK → `TruckBrand` | `PROTECT` | `trucks` | ✅ (protege marcas com caminhões) |
| `Truck.truck_model` | FK → `TruckModel` | `PROTECT` | `trucks` | ✅ |
| `TruckPhoto.truck` | FK → `Truck` | `CASCADE` | `photos` | ✅ |
| `TruckAssignment.truck` | FK → `Truck` | `PROTECT` | `assignments` | ✅ |
| `TruckAssignment.driver` | FK → `Employee` | `PROTECT` | `truck_assignments` | ✅ |
| `Visit.visitor` | FK → `Visitor` | `PROTECT` | `visits` | ✅ |
| `Visit.responsible` | FK → `Employee` | `PROTECT` | `responsible_visits` | ✅ |

### 🟡 Gap: `Truck.brand` nullable vs `save()` auto-preenche

```python
# trucks/models.py linha 86-93
brand = models.ForeignKey(
    TruckBrand, on_delete=models.PROTECT,
    related_name='trucks',
    null=True, blank=True,  # ← nullable
    verbose_name='Marca',
)
```

**Problema:** O campo `brand` é `null=True, blank=True`, mas no `save()` (linha 186-187) ele é **sempre sobrescrito** com `self.truck_model.brand`. Isso cria uma inconsistência: o schema permite `null`, mas a lógica de negócio nunca permite.

**Sugestões:**
- Opção A: Remover `null=True, blank=True` do campo `brand` e tornar obrigatório
- Opção B: Ou remover a lógica de auto-populate do `save()` e deixar o usuário escolher explicitamente

---

## 5. Meta Class

**Status: ✅ Configuração correta em todos os models**

### Análise:

| Model | `ordering` | `verbose_name` | `verbose_name_plural` | `indexes` | Extra |
|-------|-----------|----------------|----------------------|-----------|-------|
| `UserProfile` | ✅ `user__username` | ✅ | ✅ | ✅ 2 índices | — |
| `SystemLog` | ✅ `-timestamp` | ✅ | ✅ | ✅ 3 índices | — |
| `AttendanceRecord` | ✅ `-entry_time` | ✅ | ✅ | ✅ 3 índices | — |
| `PresenceEvent` | ✅ `-timestamp` | ✅ | ✅ | ✅ 2 índices | — |
| `Employee` | ✅ `name` | ✅ | ✅ | ✅ 4 índices | — |
| `BiometricTemplate` | ✅ `employee__name` | ✅ | ✅ | ✅ 2 índices | — |
| `TruckBrand` | ✅ `name` | ✅ | ✅ | ✅ 1 índice | — |
| `TruckModel` | ✅ `brand__name, name` | ✅ | ✅ | ✅ 1 índice | `unique_together` ✅ |
| `Truck` | ✅ `license_plate` | ✅ | ✅ | ✅ 4 índices | — |
| `TruckPhoto` | ✅ `order, uploaded_at` | ✅ | ✅ | ✅ 1 índice | — |
| `TruckAssignment` | ✅ `-assigned_at` | ✅ | ✅ | ✅ 3 índices | — |
| `Visitor` | ✅ `name` | ✅ | ✅ | ✅ 2 índices | — |
| `Visit` | ✅ `-visit_date, -arrival_time` | ✅ | ✅ | ✅ 3 índices | — |

### 🟡 Sugestão: `ordering` vs performance

`ordering` em campos de relacionamento causa `JOIN` adicional:

```python
# UserProfile
ordering = ['user__username']  # Gera JOIN com User toda vez que lista profiles

# BiometricTemplate
ordering = ['employee__name']  # Gera JOIN com Employee toda vez

# TruckModel
ordering = ['brand__name', 'name']  # Gera JOIN com TruckBrand
```

Se essas listagens forem frequentes, considere:
- Manter como está (os JOINs são leves com índices)
- Ou adicionar `db_constraint=False` + campo denormalizado se for gargalo comprovado

---

## 6. Proteção de Dados Sensíveis

**Status: ⚠️ Problemas identificados**

### 🔴 Crítico: `BiometricTemplate.template` sem criptografia

```python
# employees/models.py linha 99-102
template = models.BinaryField(
    verbose_name='Template',
    help_text='Dados binários do template biométrico (máx. 10 KB).',
)
```

**Problema:** Os templates biométricos são dados biométricos (PII sensível — dados pessoais sensíveis segundo a LGPD). Estão armazenados em texto plano (binário, mas sem criptografia).

**Sugestão de correção — criptografia no nível do model:**

```python
# employees/models.py
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import hashlib

class BiometricTemplate(models.Model):
    # ... campos existentes ...
    _template_encrypted = models.BinaryField(
        db_column='template_encrypted',
        verbose_name='Template (criptografado)',
        editable=False,
    )
    template = None  # Remove o campo original

    def set_template(self, raw_bytes: bytes):
        key = self._derive_key()
        f = Fernet(key)
        self._template_encrypted = f.encrypt(raw_bytes)

    def get_template(self) -> bytes:
        key = self._derive_key()
        f = Fernet(key)
        return f.decrypt(bytes(self._template_encrypted))

    @staticmethod
    def _derive_key() -> bytes:
        """Derive a Fernet key from Django SECRET_KEY + salt."""
        from django.utils.crypto import constant_time_compare
        salt = b'biometric_template_v1'
        key = hashlib.sha256(settings.SECRET_KEY.encode() + salt).digest()
        return base64.urlsafe_b64encode(key)

    def clean(self):
        # Adaptar validação para usar self._template_encrypted
        template_bytes = bytes(self._template_encrypted)
        # ... resto da validação ...
```

### 🟡 Médio: `Employee.document_photo` e `Visitor.document_photo` sem proteção

```python
# employees/models.py linha 46-51
document_photo = models.ImageField(
    upload_to='employees/documents/',
    null=True, blank=True,
)
```

**Problema:** Fotos de documentos (RG, CNH) contêm dados sensíveis e estão acessíveis via URL direta se o servidor web não tiver proteção.

**Sugestões:**

1. **Servir arquivos via Django View (com permissão):**
   ```python
   # Configurar MEDIA_URL para exigir login
   # Ou criar uma view protegida
   from django.contrib.auth.mixins import LoginRequiredMixin
   from django.http import FileResponse
   
   class ProtectedDocumentView(LoginRequiredMixin, View):
       def get(self, request, pk):
           employee = get_object_or_404(Employee, pk=pk)
           if not employee.document_photo:
               raise Http404
           return FileResponse(employee.document_photo.open(), content_type='image/jpeg')
   ```

2. **Adicionar campo `document_verified`** para rastrear verificação:
   ```python
   document_verified = models.BooleanField(default=False, verbose_name='Documento Verificado')
   ```

3. **Adicionar hash do documento para deduplicação/auditoria:**
   ```python
   document_hash = models.CharField(max_length=64, blank=True, editable=False,
       help_text='SHA-256 do documento para auditoria.')
   ```

### 🟢 Baixo: `SystemLog.ip_address` pode conter dados pessoais

```python
# accounts/models.py linha 108-112
ip_address = models.GenericIPAddressField(
    null=True, blank=True,
    verbose_name='Endereço IP',
)
```

**Sugestão:** Considere anonimizar o IP após X dias via script de limpeza:
```python
# Management command ou scheduled task
def anonymize_old_ips(days=90):
    cutoff = timezone.now() - timedelta(days=days)
    SystemLog.objects.filter(timestamp__lt=cutoff, ip_address__isnull=False).update(
        ip_address=Value(None, output_field=GenericIPAddressField())
    )
```

---

## 7. Problemas Adicionais

### 7.1. `UserProfile` sem validação de unicidade (já coberta pelo O2O)

`OneToOneField` já garante unicidade. ✅

### 7.2. `AttendanceRecord.save()` define `self.date` mas permite conflito

```python
# attendance/models.py linha 64-68
def save(self, *args, **kwargs):
    if self.entry_time is not None:
        self.date = self.entry_time.date()
    self.full_clean()
    super().save(*args, **kwargs)
```

Se `entry_time` mudar após um UPDATE, a `date` também muda. Pode ser problemático para relatórios. Considere:

```python
def save(self, *args, **kwargs):
    is_new = self.pk is None
    if is_new and self.entry_time is not None:
        self.date = self.entry_time.date()
    self.full_clean()
    super().save(*args, **kwargs)
```

### 7.3. `SystemLog.save()` bloqueia updates mas permite creates

```python
def save(self, *args, **kwargs):
    if self.pk:
        raise PermissionError('SystemLog is immutable and cannot be modified.')
    super().save(*args, **kwargs)
```

Se por alguma razão `pk` estiver setado (ex: `get_or_create` retorna objeto existente), ele levanta erro. ✅ Comportamento correto.

### 7.4. `Truck.clean()` altera `license_plate` e `chassis` para uppercase

```python
# trucks/models.py linha 181-190
def save(self, *args, **kwargs):
    if self.license_plate:
        self.license_plate = self.license_plate.upper()
    if self.chassis:
        self.chassis = self.chassis.upper()
```

Isso está no `save()`, não no `clean()`. A formatação deve ficar no `clean()` ou antes. Funciona, mas poderia ser chamado no `clean()` também para consistência.

### 7.5. `TruckPhoto.delete()` remove arquivo do disco mas não usa `storage.delete()`

```python
def delete(self, *args, **kwargs):
    self.image.delete(save=False)
    super().delete(*args, **kwargs)
```

Isso é correto ✅ (Django `FieldFile.delete()` já usa o storage configurado).

---

## Resumo das Prioridades

| Prioridade | Categoria | Impacto |
|------------|-----------|---------|
| 🔴 Crítica | `AttendanceRecord.__str__()` bug | Dados incorretos na exibição |
| 🔴 Crítica | Template biométrico sem criptografia (LGPD) | Dados sensíveis expostos no banco |
| 🟠 Alta | `UserProfile.save()` sem `full_clean()` | Validação de role pode ser pulada |
| 🟠 Alta | `TruckAssignment.save()` sem `full_clean()` | Validação de driver/truck pode ser pulada |
| 🟡 Média | `Truck.brand` nullable mas auto-preenchido | Inconsistência schema vs lógica |
| 🟡 Média | `Employee.phone` e `Visitor.phone` sem validação | Dados inconsistentes |
| 🟡 Média | Documentos de funcionários/visitantes sem proteção de acesso | Exposição de dados sensíveis |
| 🟢 Baixa | `AttendanceRecord.date` atualizada em todo save | Pode corromper relatórios históricos |
| 🟢 Baixa | `SystemLog.ip_address` não anonimizado | LGPD — direito ao esquecimento |