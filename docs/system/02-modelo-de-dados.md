# Modelo de dados

## Classificação de sensibilidade

| Classe | Significado | Exemplos neste sistema |
|---|---|---|
| 🟢 Comum | Sem restrição especial | `Truck`, `TruckBrand`, `TruckModel`, cor, placa |
| 🟡 PII (dado pessoal) | Identifica uma pessoa; exige controle de acesso | Nome, CPF, RG, telefone, endereço, foto |
| 🔴 Sensível (LGPD art. 5º II) | Dado pessoal sensível — exige base legal específica, minimização e cuidado redobrado de retenção | Template biométrico (digital) |

## Entidades por app

### `employees.Employee`
Cadastro mestre do funcionário. Campos PII: `name`, `rg`, `cpf`, `phone`, `address`, `cep`, `photo` (imagem), `document_photo` (RG/CNH/passaporte, imagem ou PDF), `foreign_document_number`/`foreign_document_type` (estrangeiros). Nenhum desses campos é criptografado no banco — a proteção é feita na camada de acesso (ver [Autenticação e controle de acesso](03-autenticacao-e-controle-de-acesso.md) e `ProtectedMediaView` para fotos/documentos).

Todo `CharField`/`TextField` de texto livre neste model tem `ProhibitNullCharactersValidator` (rejeita `\x00`) — necessário porque `models.CharField` não bloqueia esse caractere por padrão como `forms.CharField` já bloqueia; sem isso, uma criação via ORM direto (fora de um Form) só falhava no driver do banco com um erro cru.

### `visitors.Visitor` / `visitors.Visit`
Mesmo formato de PII que `Employee` (nome, RG, CPF, foto, documento). `Visit` liga um `Visitor` a um `Employee` responsável, com horário de chegada/partida prevista/real e um campo `notes` livre.

### `accounts.UserProfile`
Estende `django.contrib.auth.User` com `cpf` (texto plano, único — usado para login) e `role` (`simple`/`admin`/`master`).

### `accounts.SystemLog`
Log de auditoria **imutável** (`save()`/`delete()` levantam `PermissionError` em update/delete). Guarda `ip_address`.

### `biometric.BiometricTemplate` 🔴
```python
template = EncryptedBinaryField(max_length=10_240)  # Fernet (AES-128-CBC + HMAC-SHA256)
employee = OneToOneField(Employee)
finger_index = ...
```
Criptografado em repouso via `employee_truck_control/fields.py:EncryptedBinaryField`. Não é um hash — o template precisa ser reversível para a comparação 1:N nativa do SDK ZKFinger. Linhas gravadas antes da introdução desse campo ficam em texto plano até a migração de dados as regravar uma vez (`from_db_value` tem fallback para bytes crus se a descriptografia falhar).

### `biometric.KioskDevice`
Só persiste `token_hash` (SHA-256) + `token_prefix`. O token bruto é mostrado uma única vez na criação e nunca fica armazenado.

### `biometric.BiometricEnrollRequest`, `biometric.KioskInstallerBuild`
Metadados de workflow (fila de cadastro remoto, builds do instalador) — sem payload sensível próprio.

### `attendance.AttendanceRecord` / `attendance.PresenceEvent`
Timestamps ligados a `Employee`. Ambos efetivamente imutáveis (`delete()` levanta `PermissionError`) — correção de erro é feita por fluxo de revisão (`AttendancePendingReviewView`), não por edição direta.

### `trucks.Truck`, `TruckBrand`, `TruckModel`, `TruckAssignment`
Frota e histórico de motorista. `TruckAssignment` também é imutável na exclusão física (`delete()` bloqueado); "desassociar" é `unassigned_at` preenchido, não um delete.

## Diagrama de relacionamento (simplificado)

```
Employee ──1:1── BiometricTemplate
   │  ▲
   │  └── driver em ── TruckAssignment ── Truck ── TruckModel ── TruckBrand
   │
   ├── responsible em ── Visit ── Visitor
   │
   ├── AttendanceRecord (histórico de ponto)
   └── PresenceEvent (log bruto de cada leitura biométrica)

User ── OneToOne ── UserProfile (role, cpf)
User ── gera ── SystemLog (auditoria)

KioskDevice ── autentica ── requisições da API do kiosk (enroll/templates/scan)
```
