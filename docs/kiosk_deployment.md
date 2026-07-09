# Deploy do Quiosque Remoto de Biometria (ZK9500)

## Arquitetura

- **Servidor central**: roda o Django + banco de dados, acessível pela internet via HTTPS.
- **Quiosque**: uma máquina separada (recepção/portaria), com o leitor ZKTeco ZK9500 conectado via USB. Roda apenas o script `kiosk_agent.py` — **sem Django, sem Postgres**.
- Comunicação: o quiosque autentica em cada chamada com um **token de dispositivo** (`Authorization: Bearer <token>`), nunca com login de usuário/sessão.

Esse fluxo é **adicional** ao modo de máquina única já existente (`EmployeeEnrollView` na web + `python manage.py start_listener`), que continua funcionando normalmente para quem roda tudo no mesmo computador.

## 1. Servidor: emitir um token de dispositivo

No servidor central, com o ambiente virtual do projeto ativo:

```
python manage.py kiosk_device create --name "Recepção - Matriz"
```

O comando mostra o token **uma única vez** — copie e guarde em local seguro (ex.: gerenciador de senhas). Ele não pode ser recuperado depois; se perder, revogue e crie outro (seção 6).

Outros comandos úteis:

```
python manage.py kiosk_device list
python manage.py kiosk_device revoke --id 3
```

## 2. Pré-requisitos do servidor

- **HTTPS é obrigatório** — o token trafega no cabeçalho `Authorization`; sem TLS ele fica exposto em texto plano. Configure um proxy reverso (nginx, Caddy, etc.) ou use um provedor que já termine TLS (ex.: PythonAnywhere).
- `ALLOWED_HOSTS` deve incluir o hostname público usado pelo quiosque (variável de ambiente `DJANGO_ALLOWED_HOSTS`).
- Os 3 endpoints do quiosque (`/biometric/api/enroll/`, `/biometric/api/templates/`, `/biometric/api/scan/`) são isentos de CSRF (`csrf_exempt`) **por design** — eles autenticam via token de dispositivo, não cookie de sessão, então a proteção CSRF (que existe contra credenciais de cookie carregadas automaticamente por um navegador) não se aplica. Isso não abre uma exceção geral de CSRF no projeto — nenhuma outra view foi alterada.

## 3. Quiosque: instalação

1. Copie o repositório (ou ao menos a pasta `biometric/` + `kiosk_agent.py` + `requirements-kiosk.txt`) para a máquina do quiosque.
2. Instale o driver/SDK **ZKFinger** da ZKTeco nessa máquina (nível de sistema operacional, fora do Python) — sem ele, o `pyzkfp` não consegue falar com o leitor.
3. Crie um ambiente virtual e instale as dependências mínimas:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-kiosk.txt
   ```
4. Crie um arquivo `.env` na mesma pasta do `kiosk_agent.py`:
   ```
   KIOSK_SERVER_URL=https://seu-servidor.exemplo.com
   KIOSK_DEVICE_TOKEN=<token copiado no passo 1>
   KIOSK_DEVICE_ID=0
   KIOSK_TEMPLATE_REFRESH_SECONDS=300
   KIOSK_HTTP_TIMEOUT=10
   ```

## 4. Cadastrar uma digital (a partir do quiosque)

Com o leitor conectado:

```
python kiosk_agent.py enroll --employee-id 42
```

Pede 3 toques do mesmo dedo (com o dedo levantado entre um toque e outro), mescla as amostras e envia o template pronto para o servidor via `/biometric/api/enroll/`.

## 5. Rodar o reconhecimento contínuo

```
python kiosk_agent.py listen
```

Mantém uma sincronização periódica (padrão a cada 5 minutos) da lista de digitais cadastradas de funcionários ativos, identifica localmente cada toque no leitor e reporta o evento (entrada/saída) ao servidor via `/biometric/api/scan/`. `Ctrl+C` encerra graciosamente.

## 6. Rodar como serviço resiliente no Windows

Para sobreviver a reinícios do computador e a travamentos do processo, use uma das opções:

**Opção A — Agendador de Tarefas (Task Scheduler)**
- Gatilho: "Ao iniciar o sistema" ou "Ao fazer logon".
- Ação: `pythonw.exe C:\quiosque\kiosk_agent.py listen` (usar o `pythonw.exe` do `.venv` criado acima).
- Marcar "Executar estando o usuário conectado ou não".
- Na aba "Configurações": "Reiniciar a cada 1 minuto, até 3 tentativas" em caso de falha.

**Opção B — NSSM (Non-Sucking Service Manager)**
```
nssm install ZK9500Kiosk "C:\quiosque\.venv\Scripts\python.exe" "C:\quiosque\kiosk_agent.py listen"
nssm set ZK9500Kiosk AppDirectory C:\quiosque
nssm set ZK9500Kiosk AppRestartDelay 5000
nssm start ZK9500Kiosk
```

## 7. Rotação de token

```
python manage.py kiosk_device revoke --id 3
python manage.py kiosk_device create --name "Recepção - Matriz"
```

Atualize o `.env` do quiosque com o novo token e reinicie o serviço/processo.

## 8. Limitações conhecidas (v1)

- **Sem fila offline**: se o quiosque perder conexão com o servidor no momento de um toque, o evento é registrado no log local e **descartado** — não há retentativa automática nem fila de reenvio.
- **Atraso de sincronização**: um funcionário recém-cadastrado ou reativado pode levar até `KIOSK_TEMPLATE_REFRESH_SECONDS` (padrão 5 min) para ser reconhecido pelo quiosque.
- **Sem interface de gestão de dispositivos**: criação/revogação de tokens é só via linha de comando (`kiosk_device`), sem tela administrativa.
