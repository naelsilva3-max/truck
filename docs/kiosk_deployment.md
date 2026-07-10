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

O comando mostra o token **uma única vez** — copie e guarde em local seguro (ex.: gerenciador de senhas). Ele não pode ser recuperado depois; se perder, revogue e crie outro (seção 7).

Outros comandos úteis:

```
python manage.py kiosk_device list
python manage.py kiosk_device revoke --id 3
```

**Alternativa sem SSH**: um usuário com role `master` também pode gerar um token pelo próprio site, em **Sistema → Gerar Token de Quiosque** (`/biometric/kiosk-token/`) — mesma informação de `kiosk_device list`, e o token só é mostrado uma vez, igual ao comando.

## 2. Pré-requisitos do servidor

- **HTTPS é obrigatório** — o token trafega no cabeçalho `Authorization`; sem TLS ele fica exposto em texto plano. Configure um proxy reverso (nginx, Caddy, etc.) ou use um provedor que já termine TLS (ex.: PythonAnywhere).
- `ALLOWED_HOSTS` deve incluir o hostname público usado pelo quiosque (variável de ambiente `DJANGO_ALLOWED_HOSTS`).
- Os 3 endpoints do quiosque (`/biometric/api/enroll/`, `/biometric/api/templates/`, `/biometric/api/scan/`) são isentos de CSRF (`csrf_exempt`) **por design** — eles autenticam via token de dispositivo, não cookie de sessão, então a proteção CSRF (que existe contra credenciais de cookie carregadas automaticamente por um navegador) não se aplica. Isso não abre uma exceção geral de CSRF no projeto — nenhuma outra view foi alterada.

## 3. Quiosque: instalação

### Opção A — instalador `.exe` (recomendado)

`kiosk_installer/` tem um instalador gráfico ("Avançar, Avançar, Concluir") que faz os passos 2-6 abaixo sozinho: copia os binários (Python + dependências já embutidos, não precisa instalar Python na máquina do quiosque), escreve o `.env`, registra e inicia a Tarefa Agendada.

1. Gerar o instalador (nesta máquina de desenvolvimento, com o venv do projeto e o Inno Setup instalados — `winget install JRSoftware.InnoSetup`):
   ```
   powershell -ExecutionPolicy Bypass -File kiosk_installer\build.ps1
   ```
   Gera `kiosk_installer\output\ZK9500KioskSetup.exe`.
2. Copie esse `.exe` para a máquina do quiosque (pendrive, rede, etc.) e rode-o lá.
3. **Pré-requisito que o instalador não resolve sozinho**: o driver/SDK **ZKFinger** da ZKTeco precisa já estar instalado nessa máquina (nível de sistema operacional, fora do instalador) — sem ele, o quiosque não fala com o leitor mesmo depois de instalado. O wizard mostra um lembrete, mas não instala nem verifica automaticamente.
4. No wizard: cole a URL do servidor e o token do dispositivo (gerado no passo 1 da seção anterior, ou pela página **Sistema → Gerar Token de Quiosque**).
5. Pronto — a Tarefa Agendada `ZK9500KioskListener` já fica registrada e rodando. Atalhos no Menu Iniciar: "Cadastrar biometria (manual)" e "Ver logs".

**Nota sobre o Smart App Control do Windows 11**: como o instalador não é assinado digitalmente, o Smart App Control (quando ativado) pode bloquear a execução sem nem oferecer a opção "Executar assim mesmo" do SmartScreen. Se isso acontecer, é preciso desativá-lo em Configurações → Privacidade e segurança → Segurança do Windows → Controle de aplicativos e navegador — **atenção: uma vez desativado, só volta a ativar reinstalando o Windows**.

### Opção B — manual (a partir do código-fonte)

1. Copie o repositório (ou ao menos a pasta `biometric/` + `kiosk_agent.py` + `requirements-kiosk.txt`) para a máquina do quiosque.
2. Instale o driver/SDK **ZKFinger** da ZKTeco nessa máquina (nível de sistema operacional, fora do Python) — sem ele, o `pyzkfp` não consegue falar com o leitor.
3. Instale **Python** na máquina do quiosque, crie um ambiente virtual e instale as dependências mínimas:
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
   KIOSK_TEMPLATE_REFRESH_SECONDS=30
   KIOSK_ENROLL_POLL_SECONDS=5
   KIOSK_HTTP_TIMEOUT=10
   ```

## 4. Cadastrar uma digital (a partir do quiosque)

Com o leitor conectado:

```
python kiosk_agent.py enroll --employee-id 42
```

Pede 3 toques do mesmo dedo (com o dedo levantado entre um toque e outro), mescla as amostras e envia o template pronto para o servidor via `/biometric/api/enroll/`.

## 4.1 Cadastro remoto disparado pelo site (fila de pedidos)

Além do comando manual acima, o botão "Cadastrar Biometria" no site funciona mesmo quando o servidor Django não tem leitor físico (ex.: rodando num VPS) — o clique cria um pedido pendente que o quiosque atende sozinho, sem nenhum comando manual:

1. Um admin clica "Cadastrar Biometria" na página de um funcionário. Como o servidor não acha um leitor local, em vez de só mostrar erro ele grava um `BiometricEnrollRequest` pendente e a página passa a mostrar "Aguardando leitor do quiosque remoto...", atualizando sozinha (polling AJAX a cada 3s).
2. O `kiosk_agent.py listen`, que já está rodando continuamente no quiosque (seção 5), consulta `GET /biometric/api/enroll-requests/next/` a cada `KIOSK_ENROLL_POLL_SECONDS` (padrão 5s, ver seção 3).
3. Ao encontrar um pedido pendente, ele pausa a escuta normal de ponto, pede 3 toques do dedo (mesmo fluxo do `enroll` manual), envia o template para `/biometric/api/enroll/` (incluindo o id do pedido), e retoma a escuta normal — tudo automaticamente.
4. A página do site detecta a conclusão no próximo poll e recarrega, mostrando o status atualizado.

Se o quiosque estiver offline ou ninguém aparecer no leitor, o pedido continua pendente e será tentado de novo a cada ciclo — não há expiração automática (ver seção 8). O admin pode clicar "Cancelar solicitação" na própria página a qualquer momento.

## 5. Rodar o reconhecimento contínuo

```
python kiosk_agent.py listen
```

Mantém uma sincronização periódica (padrão a cada 5 minutos) da lista de digitais cadastradas de funcionários ativos, identifica localmente cada toque no leitor e reporta o evento (entrada/saída) ao servidor via `/biometric/api/scan/`. `Ctrl+C` encerra graciosamente.

## 6. Rodar como serviço resiliente no Windows

Se instalou pela **Opção A** (instalador `.exe`) da seção 3, isso já está feito — pule esta seção. As opções abaixo são para quem instalou manualmente (Opção B).

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
- **Atraso de sincronização**: um funcionário recém-cadastrado, reativado, ou que teve a biometria apagada, pode levar até `KIOSK_TEMPLATE_REFRESH_SECONDS` (padrão 30s) para o quiosque (des)reconhecê-lo — o quiosque só compara contra o último cache local, sem saber do estado atual do servidor entre sincronizações. Funcionário **desativado** (`is_active=False`) tem uma segunda barreira no servidor (`/api/scan/` rejeita com 409 mesmo se o quiosque ainda reconhecer localmente); funcionário ativo com biometria apenas apagada não tem essa segunda barreira hoje.
- **Sem interface de gestão de dispositivos**: criação/revogação de tokens é só via linha de comando (`kiosk_device`), sem tela administrativa.
- **Pedidos de cadastro remoto (seção 4.1) não expiram sozinhos**: se o quiosque ficar offline por muito tempo, o pedido fica pendente indefinidamente até alguém cancelar manualmente pela página do site.
- **Um único quiosque físico é assumido**: não há coordenação se mais de um `kiosk_agent.py listen` fizer polling da mesma fila de pedidos ao mesmo tempo (o endpoint só devolve o pedido mais antigo, sem "reservá-lo").
- **Retentativa sem backoff**: se ninguém aparecer no leitor para um pedido pendente, o quiosque tenta capturar de novo a cada `KIOSK_ENROLL_POLL_SECONDS`, até o pedido ser atendido ou cancelado.
- **Instalador não assinado**: sem certificado de code signing, o Windows (SmartScreen e/ou Smart App Control) trata o `.exe` como desconhecido na primeira execução — ver nota na seção 3.
- **Local de `.env`/log difere por modo de instalação**: pela Opção A (instalador), fica em `%LOCALAPPDATA%\ZK9500Kiosk\` (Program Files não é gravável pela Tarefa Agendada, que roda com o token do usuário logado, não elevado); pela Opção B (manual), fica na mesma pasta do `kiosk_agent.py`.
