# Deploy e operação

> Nenhum valor real (IP, senha, chave) aparece neste documento — todos os exemplos usam placeholders (`<...>`). Segredos reais vivem só no `.env` de cada ambiente, fora do controle de versão.

## Arquitetura de deploy

Deploy simples, pull-based, um único VPS:

```
git pull → ativa venv → pip install -r requirements.txt → manage.py migrate
→ manage.py collectstatic → systemctl restart gunicorn
```

Script: `deploy/deploy.sh`, rodado a partir da raiz do repo na VPS (usuário não-root dedicado, ex. `deploy`). Não há blue/green nem rollback automático — em caso de problema, o rollback é `git checkout <commit-anterior>` seguido de rodar o script de novo.

Gunicorn roda como serviço systemd (`deploy/gunicorn.service`), 3 workers, bind num socket Unix (não numa porta TCP), lendo segredos de `EnvironmentFile=<caminho-do-.env-em-produção>`.

Nginx (`deploy/nginx.conf`) faz proxy reverso de `/` para o socket do gunicorn, serve `/static/` diretamente, e **não** serve `/media/` diretamente — isso passa pela `ProtectedMediaView` do Django (autenticação obrigatória), que devolve os bytes de volta ao nginx via `X-Accel-Redirect` numa location `internal;` (`/protected-media/`) — eficiente (nginx serve o arquivo) e seguro (Django decide quem pode ver).

**TLS**: o `nginx.conf` do repositório só tem `listen 80` — terminação HTTPS (obrigatória para o kiosk, que manda o token no header `Authorization`) precisa ser configurada à parte na VPS (ex. certbot/Let's Encrypt), não está no arquivo versionado.

## Variáveis de ambiente (`.env` de produção)

| Variável | Uso | Obrigatória |
|---|---|---|
| `DJANGO_SECRET_KEY` | Chave secreta do Django | Sim |
| `DJANGO_DEBUG` | `False` em produção | Sim |
| `DJANGO_ALLOWED_HOSTS` | Hostname público (inclui o usado pelo kiosk) | Sim |
| `BIOMETRIC_ENCRYPTION_KEY` | Chave Fernet para criptografar templates biométricos | Sim |
| `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexão com PostgreSQL | Sim |
| `DB_POOL_ENABLED`, `DB_POOL_MAX_SIZE`, `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` | Pool de conexões (opcional) | Não |
| `DB_SSL_MODE`, `DB_SSL_CERT`, `DB_SSL_KEY`, `DB_SSL_ROOT_CERT` | TLS na conexão com o banco (se `DB_POOL_ENABLED`) | Não |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Verificação de e-mail de usuário | Sim, se a feature de verificação estiver em uso |

Nunca commitar o `.env` — ele já está fora do controle de versão (`.gitignore`); isso vale também para qualquer `.env` gerado dentro de um instalador de kiosk distribuído (ver [Arquitetura do kiosk](05-arquitetura-kiosk.md)).

## Backup

`deploy/backup_db.sh`, agendado via cron do usuário `deploy` (sugestão no próprio script: `0 3 * * *`):

1. Lê as credenciais do banco chamando `settings.DATABASES` do próprio Django (evita problemas de escaping de shell que um `source .env` teria com caracteres especiais no `SECRET_KEY`).
2. Roda `pg_dump --format=custom`.
3. Retenção: mantém só os últimos 14 dias (`find ... -mtime +14 -delete`).

Não há cópia para armazenamento externo/off-site no script — os dumps ficam só no disco local da VPS. Considerar isso ao planejar recuperação de desastre.

## Restauração

Não há script pronto de restore. Fluxo manual:
```
pg_restore --host=<host> --port=<porta> --username=<usuario> --dbname=<nome-do-banco> --clean <arquivo.dump>
```

## Como rodar o deploy

```
ssh <usuario>@<host-da-vps>
cd <caminho-do-repo>
./deploy/deploy.sh
```

Os scripts em `deploy/*.sh` precisam do bit de execução (`chmod +x`). Se o repositório for editado a partir de um filesystem Windows, vale conferir com `git ls-files -s deploy/` (deve mostrar `100755`, não `100644`) antes de rodar `./deploy/deploy.sh` na VPS.
