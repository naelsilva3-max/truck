# Autenticação e controle de acesso

## Login

Sessão padrão do Django, mas o formulário de login (`accounts/forms.py:CPFOrUsernameAuthenticationForm`) aceita **CPF ou nome de usuário** — resolve o CPF para o `username` correspondente antes de delegar para a autenticação padrão do Django (`accounts/views.py:CPFLoginView`).

## Papéis (roles)

`UserProfile.role` tem três valores, aplicados via mixins em `accounts/mixins.py`:

| Role | Mixin | Pode |
|---|---|---|
| `simple` | `RoleRequiredMixin` | Ver listagens, detalhes, relatórios — somente leitura |
| `admin` | `EditRequiredMixin` | Tudo do `simple` + criar/editar registros (funcionário, visitante, caminhão, motorista) |
| `master` | `MasterRequiredMixin` | Tudo do `admin` + gestão de usuários, log do sistema, revisão de ponto pendente, tokens/instaladores de kiosk |

`request.user.is_superuser` é tratado como `master` implícito (`get_role()`).

## Tabela de views por permissão exigida

| Área | Leitura | Escrita (criar/editar) | Extra |
|---|---|---|---|
| `employees` | `LoginRequiredMixin` | `EditRequiredMixin` | — |
| `trucks` | `LoginRequiredMixin` | `EditRequiredMixin` | — |
| `visitors` | `LoginRequiredMixin` | `EditRequiredMixin` | — |
| `attendance` | `LoginRequiredMixin` (lista, calendário, histórico) | — | Revisão de pendências: `MasterRequiredMixin` |
| `accounts` (gestão de usuário) | `MasterRequiredMixin` | `MasterRequiredMixin` | — |
| `biometric` (kiosk token/instalador) | `MasterRequiredMixin` | `MasterRequiredMixin` | — |
| `biometric` (API do kiosk) | `DeviceTokenAuthMixin` (token de dispositivo, não sessão) | idem | `csrf_exempt` por design — ver [Fluxo biométrico](04-fluxo-biometrico.md) |

Os templates já escondem botões de escrita para quem não tem `can_edit` (context processor `accounts/context_processors.py`), mas isso é só UX — a garantia real é o mixin no view. Não confie em esconder botão como controle de acesso.

## Rate limiting

- **Login**: `employee_truck_control/rate_limit.py:LoginRateLimitMiddleware` — 10 tentativas/10min por IP (bloqueio de 10min) e 15/15min por conta (bloqueio de 15min).
- **API do kiosk**: `biometric/auth.py:DeviceTokenAuthMixin` — throttle em memória por IP, 10 falhas/10min → bloqueio de 10min.
- Nenhuma outra view de escrita (ex.: criação de visitante) tem rate limit dedicado hoje.

## Outras proteções

- **`BiometricTemplateProtectionMiddleware`** (`employee_truck_control/middleware.py`): impede que uma instância de `BiometricTemplate` chegue a um contexto de template por engano — levanta `PermissionError` se isso acontecer. Defesa contra vazamento acidental do template criptografado numa página HTML.
- **`ContentSecurityPolicyMiddleware`**: define um header CSP real (`unsafe-inline` mantido deliberadamente — não há bundler de JS no projeto).
- **`ProtectedMediaView`** (`employee_truck_control/urls.py` → `/media/<path>`): fotos e documentos (funcionário, visitante) não são servidos diretamente pelo nginx — passam por essa view (login obrigatório, checagem de path traversal) que delega o byte-serving de volta ao nginx via `X-Accel-Redirect` (`internal;` no nginx, ver [Deploy e operação](06-deploy-e-operacao.md)).

## Não coberto hoje

Ver [Controles de acesso e gaps conhecidos](08-controles-de-acesso-e-gaps-conhecidos.md) para os itens ainda em aberto.
