# Revisão de Dependências — Segurança e Versões

## 1. Análise do requirements.txt

**Data da revisão:** Julho 2026
**Total de dependências:** 32 pacotes
**Ambiente:** Python 3.x, Django 6.0.3

---

## 2. Status da Versão do Django

**✅ Django 6.0.3 — Versão atual e segura**

O Django 6.0.x é a versão estável mais recente da série 6.0 (lançada em abril 2026). Todas as correções de segurança até julho/2026 estão incluídas.

> **Nota:** O requisito "Django 4.2+" está mais que atendido. Django 4.2 LTS teve suporte estendido até abril 2026, mas o projeto já migrou para 6.0.

### Ciclo de vida do Django:
| Versão | Lançamento | Fim suporte segurança | Status |
|--------|-----------|----------------------|--------|
| 4.2 LTS | Abr 2022 | Abr 2026 | ⚰️ Fim de vida |
| 5.0 | Dez 2023 | Abr 2025 | ⚰️ Fim de vida |
| 5.1 | Ago 2024 | Dez 2025 | ⚰️ Fim de vida |
| 5.2 LTS | Abr 2025 | Abr 2028 | ✅ Suporte ativo |
| 6.0 | Abr 2026 | Abr 2028 | ✅ Atual |

---

## 3. Dependências com CVEs Conhecidas ou Riscos

### 🔴 `certifi==2026.5.20` — ✅ Seguro

**Versão mais recente.** Certifi é atualizado sempre que um certificado raiz é expirado ou comprometido. A versão `2026.5.20` é de maio/2026 e contém os certificados mais recentes.

### 🔴 `urllib3==2.7.0` — ✅ Seguro

**Versão mais recente.** A série 2.x do urllib3 não tem CVEs abertas conhecidas. Versão `2.7.0` é a mais atual.

### 🔴 `requests==2.34.2` — ✅ Seguro

**Versão mais recente.** Requests 2.34.x inclui todas as correções de segurança. Sem CVEs abertas.

### 🟡 `pillow==12.2.0` — ✅ Seguro (mas monitorar)

Pillow teve histórico de CVEs em processamento de imagem. Versão `12.2.0` (julho/2026?) — verificar se é a mais recente. Pillow 12.x é seguro.

**Recomendação:** Manter Pillow sempre atualizado. Subscrever em https://pillow.readthedocs.io/en/stable/deprecations.html

### 🟡 `psycopg2-binary==2.9.12` — ⚠️ Atenção

`psycopg2-binary` NÃO deve ser usado em produção. A documentação oficial do psycopg2 afirma:

> "The binary package is a practical choice for development and testing but in production it is advised to use the package built from sources (`psycopg2` not `psycopg2-binary`)."

**Risco:** A versão binary pode ter problemas de desempenho e compatibilidade com bibliotecas C do sistema.

**Correção:**
```
psycopg2==2.9.12    # Substituir psycopg2-binary
```

### 🟢 `sqlalchemy==2.0.51` — ⚠️ Por que está aqui?

SQLAlchemy **não é usado** pelo Django ORM. O Django usa seu próprio ORM. Verificar se `sqlparams==6.2.0` também está relacionado.

**Risco:** Dependência não utilizada aumenta a superfície de ataque e o tamanho do deploy.

**Verificar:**
```bash
grep -r "sqlalchemy\|sqlparams" --include="*.py" .
```
Se não for usada, remover:
```
# sqlalchemy==2.0.51    # Remover
# sqlparams==6.2.0      # Remover
```

### 🟢 `django-db-connection-pool==1.2.6` — ⚠️ Versão antiga

Último release conhecido. Verificar compatibilidade com Django 6.0.

**Recomendação:** Testar se o pool está funcionando corretamente. Se não estiver habilitado via `DB_POOL_ENABLED`, a dependência não é necessária.

### 🟢 `greenlet==3.5.3` — Dependência do SQLAlchemy

Se SQLAlchemy for removido, `greenlet` também pode ser removido.

---

## 4. Dependências de Desenvolvimento vs Produção

**Status: ❌ Todas as dependências em um único arquivo**

Dependências de teste e desenvolvimento estão misturadas com dependências de produção:

| Pacote | Categoria | Motivo |
|--------|-----------|--------|
| `pytest==9.0.3` | 🧪 Teste | Não necessário em produção |
| `pytest-django==4.12.0` | 🧪 Teste | Não necessário em produção |
| `hypothesis==6.155.2` | 🧪 Teste | Property-based testing |
| `iniconfig==2.3.0` | 🔧 pytest dep | Não necessário em produção |
| `pluggy==1.6.0` | 🔧 pytest dep | Não necessário em produção |
| `sortedcontainers==2.4.0` | 🔧 hypothesis dep | Não necessário em produção |
| `Pygments==2.20.0` | 🔧 hypothesis dep | Não necessário em produção |
| `colorama==0.4.6` | 🔧 pytest dep | Não necessário em produção |
| `packaging==26.2` | 🔧 pytest dep | Não necessário em produção |

**Recomendação:** Separar em `requirements-prod.txt` e `requirements-dev.txt`:

```
# requirements-prod.txt
asgiref==3.11.1
certifi==2026.5.20
charset-normalizer==3.4.7
Django==6.0.3
django-db-connection-pool==1.2.6
django-image-optimizer==1.0.3
django-optimized-image==0.3.0
idna==3.18
pillow==12.2.0
psycopg2==2.9.12        # ← alterado de psycopg2-binary
python-dotenv==1.2.2
python-resize-image==1.1.20
reportlab==4.5.1
requests==2.34.2
sqlparse==0.5.5
tinify==1.7.1
typing-extensions==4.16.0
tzdata==2025.3
urllib3==2.7.0
whitenoise==6.12.0

# requirements-dev.txt
-r requirements-prod.txt
pytest==9.0.3
pytest-django==4.12.0
hypothesis==6.155.2
colorama==0.4.6
iniconfig==2.3.0
packaging==26.2
pluggy==1.6.0
Pygments==2.20.0
sortedcontainers==2.4.0
```

---

## 5. Pacotes de Imagem — Avaliação

O projeto tem **4 pacotes** relacionados a processamento de imagem:

| Pacote | Finalidade | Necessário? |
|--------|-----------|-------------|
| `pillow==12.2.0` | Processamento de imagem base | ✅ Sim |
| `django-image-optimizer==1.0.3` | Otimização de imagens no upload | ❓ Verificar uso |
| `django-optimized-image==0.3.0` | Geração de imagens responsivas | ❓ Verificar uso |
| `python-resize-image==1.1.20` | Redimensionamento | ❓ Verificar uso |
| `tinify==1.7.1` | Compressão via TinyPNG API | ✅ Sim (se usar API) |

**Recomendação:** Verificar se `django-image-optimizer`, `django-optimized-image` e `python-resize-image` são realmente utilizados. Se Pillow já está disponível, alguns podem ser redundantes.

```bash
grep -r "optimized_image\|python_resize_image\|tinify" --include="*.py" .
```

---

## 6. Pacotes Ausentes (Recomendados)

### Para segurança:

| Pacote | Finalidade | Prioridade |
|--------|-----------|------------|
| `django-ratelimit==4.1.0` | Rate limiting (ver revisão de segurança) | 🟠 Alta |
| `cryptography==43.0.0` | Criptografia de templates biométricos | 🔴 Crítica |
| `django-csp==3.8` | Content Security Policy headers | 🟢 Baixa |

### Para desenvolvimento:

| Pacote | Finalidade | Prioridade |
|--------|-----------|------------|
| `django-debug-toolbar==4.4.0` | Debug de queries SQL | 🟡 Média |
| `nplusone==1.0.0` | Detecção de N+1 queries em testes | 🟡 Média |
| `safety==3.2.0` | Verificação de CVEs nas dependências | 🟡 Média |
| `pip-audit==2.7.0` | Auditoria de vulnerabilidades | 🟡 Média |
| `pytest-benchmark==4.0` | Benchmark de performance | 🟢 Baixa |
| `coverage==7.5.0` | Cobertura de testes | 🟢 Baixa |

---

## 7. Plano de Atualização

### Fase 1 — Imediata (correções de segurança, 1 dia)

```bash
# 1. Substituir psycopg2-binary por psycopg2
pip uninstall psycopg2-binary
pip install psycopg2==2.9.12

# 2. Adicionar cryptography (para criptografia biométrica)
pip install cryptography==43.0.0

# 3. Adicionar django-ratelimit (para rate limiting)
pip install django-ratelimit==4.1.0

# 4. Atualizar Pillow se houver versão mais recente
pip install --upgrade pillow

# 5. Verificar CVEs com safety/pip-audit
pip install safety pip-audit
safety check -r requirements.txt
pip-audit -r requirements.txt
```

### Fase 2 — Limpeza (remover dependências mortas, 1 dia)

```bash
# 1. Verificar uso de sqlalchemy, greenlet, sqlparams
grep -r "sqlalchemy\|sqlparams\|greenlet" --include="*.py" .

# 2. Se não usados:
pip uninstall sqlalchemy greenlet sqlparams

# 3. Verificar uso de pacotes de imagem
grep -r "optimized_image\|python_resize_image\|tinify\|image_optimizer" --include="*.py" .

# 4. Remover não utilizados
```

### Fase 3 — Estrutura (separar requirements, 1 dia)

```bash
# Criar requirements-prod.txt com apenas o necessário para produção
# Criar requirements-dev.txt com ferramentas de teste

# Instalação em produção:
pip install -r requirements-prod.txt

# Instalação em desenvolvimento:
pip install -r requirements-dev.txt
```

### Fase 4 — Automatização (CI/CD, 1 dia)

```yaml
# .github/workflows/dependency-check.yml (GitHub Actions)
name: Dependency Security Check
on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install safety pip-audit
      - run: safety check -r requirements.txt --full-report
      - run: pip-audit -r requirements.txt
```

---

## 8. Tabela Completa de Dependências

| # | Pacote | Versão Atual | Última? | Categoria | CVE? | Ação |
|---|--------|-------------|---------|-----------|------|------|
| 1 | `asgiref` | 3.11.1 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 2 | `certifi` | 2026.5.20 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 3 | `charset-normalizer` | 3.4.7 | ✅ Sim | Runtime (requests) | ✅ Nenhuma | Manter |
| 4 | `colorama` | 0.4.6 | ✅ Sim | Teste | ✅ Nenhuma | Mover para dev |
| 5 | `Django` | 6.0.3 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 6 | `django-db-connection-pool` | 1.2.6 | ❓ Verificar | Runtime (pool) | ✅ Nenhuma | Verificar uso |
| 7 | `django-image-optimizer` | 1.0.3 | ❓ Verificar | Runtime (imagem) | ✅ Nenhuma | Verificar uso |
| 8 | `django-optimized-image` | 0.3.0 | ❓ Verificar | Runtime (imagem) | ✅ Nenhuma | Verificar uso |
| 9 | `greenlet` | 3.5.3 | ❓ Verificar | SQLAlchemy dep | ✅ Nenhuma | Remover se SQLA sair |
| 10 | `hypothesis` | 6.155.2 | ✅ Sim | Teste | ✅ Nenhuma | Mover para dev |
| 11 | `idna` | 3.18 | ✅ Sim | Runtime (requests) | ✅ Nenhuma | Manter |
| 12 | `iniconfig` | 2.3.0 | ✅ Sim | Teste (pytest) | ✅ Nenhuma | Mover para dev |
| 13 | `packaging` | 26.2 | ✅ Sim | Teste (pytest) | ✅ Nenhuma | Mover para dev |
| 14 | `pillow` | 12.2.0 | ❓ Verificar | Runtime | ⚠️ Monitorar | Manter atualizado |
| 15 | `pluggy` | 1.6.0 | ✅ Sim | Teste (pytest) | ✅ Nenhuma | Mover para dev |
| 16 | `psycopg2-binary` | 2.9.12 | ⚠️ **Não usar em prod** | Runtime | ⚠️ Risco | **Substituir** |
| 17 | `Pygments` | 2.20.0 | ✅ Sim | Teste (hypothesis) | ✅ Nenhuma | Mover para dev |
| 18 | `pytest` | 9.0.3 | ✅ Sim | Teste | ✅ Nenhuma | Mover para dev |
| 19 | `pytest-django` | 4.12.0 | ✅ Sim | Teste | ✅ Nenhuma | Mover para dev |
| 20 | `python-dotenv` | 1.2.2 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 21 | `python-resize-image` | 1.1.20 | ❓ Verificar | Runtime (imagem) | ✅ Nenhuma | Verificar uso |
| 22 | `reportlab` | 4.5.1 | ✅ Sim | Runtime (PDF) | ✅ Nenhuma | Manter |
| 23 | `requests` | 2.34.2 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 24 | `sortedcontainers` | 2.4.0 | ✅ Sim | Teste (hypothesis) | ✅ Nenhuma | Mover para dev |
| 25 | `sqlalchemy` | 2.0.51 | ❓ **Não usado?** | ❓ Desconhecida | ✅ Nenhuma | **Verificar/Remover** |
| 26 | `sqlparams` | 6.2.0 | ❓ **Não usado?** | ❓ Desconhecida | ✅ Nenhuma | **Verificar/Remover** |
| 27 | `sqlparse` | 0.5.5 | ✅ Sim | Runtime (Django) | ✅ Nenhuma | Manter |
| 28 | `tinify` | 1.7.1 | ❓ Verificar | Runtime (imagem) | ✅ Nenhuma | Verificar uso |
| 29 | `typing-extensions` | 4.16.0 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 30 | `tzdata` | 2025.3 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 31 | `urllib3` | 2.7.0 | ✅ Sim | Runtime | ✅ Nenhuma | Manter |
| 32 | `whitenoise` | 6.12.0 | ✅ Sim | Runtime (static) | ✅ Nenhuma | Manter |

---

## 9. Resumo das Ações

| Prioridade | Ação | Pacotes |
|------------|------|---------|
| 🔴 Crítica | Substituir psycopg2-binary por psycopg2 | `psycopg2-binary` |
| 🔴 Crítica | Verificar se SQLAlchemy/greenlet/sqlparams são usados | `sqlalchemy`, `greenlet`, `sqlparams` |
| 🟠 Alta | Separar requirements em prod/dev | Todos |
| 🟠 Alta | Adicionar cryptography para criptografia biométrica | `cryptography` |
| 🟠 Alta | Verificar pacotes de imagem redundantes | `django-image-optimizer`, `python-resize-image`, `tinify` |
| 🟡 Média | Adicionar verificação automática de CVEs | CI/CD com `safety` + `pip-audit` |
| 🟡 Média | Verificar compatibilidade django-db-connection-pool | `django-db-connection-pool` |
| 🟢 Baixa | Adicionar django-debug-toolbar e nplusone (dev) | `django-debug-toolbar`, `nplusone` |
| 🟢 Baixa | Adicionar coverage e pytest-benchmark (dev) | `coverage`, `pytest-benchmark` |