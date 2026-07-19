# Visão geral

## O que o sistema faz

Aplicação Django (`employee_truck_control`) que centraliza, para uma empresa com frota própria:

- Cadastro de **funcionários** e seus documentos/foto
- **Ponto eletrônico** por biometria de digital (leitor ZKTeco ZK9500)
- Cadastro e **controle de acesso de visitantes** (check-in/check-out, crachá em PDF)
- Cadastro de **caminhões** e histórico de atribuição de motorista
- Um **kiosk remoto** (máquina separada, sem Django) que roda o leitor biométrico na portaria e fala com o servidor central por API com token de dispositivo

## Apps Django

| App | Responsabilidade |
|---|---|
| `accounts` | Autenticação (login por CPF ou usuário), papéis de usuário, log de auditoria imutável |
| `employees` | Cadastro de funcionário (dados, foto, documento) e enrolamento biométrico |
| `attendance` | Registro de ponto (entrada/almoço/saída) e histórico de presença |
| `biometric` | Integração com o leitor ZKTeco, armazenamento criptografado do template, API do kiosk |
| `trucks` | Frota de caminhões e atribuição de motorista |
| `visitors` | Cadastro de visitante e registro de visitas (chegada/partida) |
| `core` | Vazio — placeholder, sem models/views |
| `kiosk_installer` | Não é um app Django — projeto de empacotamento (PyInstaller + Inno Setup) do `kiosk_agent.py` num instalador Windows |

## Como as peças se conectam

```
┌─────────────────────────────┐         HTTPS + token de dispositivo        ┌──────────────────────┐
│   Kiosk remoto (portaria)   │ ───────────────────────────────────────────▶│   Servidor Django     │
│   kiosk_agent.py            │◀─────────────────────────────────────────── │   (este repositório)  │
│   (sem Django, sem Postgres)│   /biometric/api/enroll|templates|scan/     │   + PostgreSQL         │
└─────────────────────────────┘                                            └──────────┬────────────┘
                                                                                        │
                                                                             sessão de usuário (cookie)
                                                                                        │
                                                                             ┌──────────▼────────────┐
                                                                             │  Navegador (RH, portaria,│
                                                                             │  gestores) — CRUD normal │
                                                                             └──────────────────────────┘
```

Duas formas de operar a biometria coexistem (ver [Fluxo biométrico](04-fluxo-biometrico.md)):

1. **Máquina única**: o próprio servidor tem o leitor conectado (`python manage.py start_listener`).
2. **Kiosk remoto**: uma máquina separada roda `kiosk_agent.py` e fala com o servidor via API (ver [Arquitetura do kiosk](05-arquitetura-kiosk.md)).

## Stack

- Django 6.0, PostgreSQL (via `psycopg2-binary`, pool opcional com `django-db-connection-pool`)
- `gunicorn` + `nginx` em produção (ver [Deploy e operação](06-deploy-e-operacao.md))
- `pyzkfp` (SDK ZKFinger da ZKTeco) para o leitor biométrico — com fallback automático (`UnavailableBackend`) quando o driver/hardware não está presente
- `pytest` + `pytest-django` + `hypothesis` (testes baseados em propriedades) para a suíte de testes
