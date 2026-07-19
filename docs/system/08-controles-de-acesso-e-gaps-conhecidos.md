# Controles de acesso e gaps conhecidos

Lista do que está **hoje** em aberto no código — não um histórico de bugs corrigidos (esses estão no `git log`, não aqui). Revisar esta lista contra o código antes de citá-la em qualquer lugar: se um item foi corrigido depois da última atualização deste arquivo, o código manda, não este documento.

## Em aberto

### `UserCreateView` sem validação de força de senha
`accounts/views.py:UserCreateView` cria usuário com validação manual (checagem própria de campos), sem passar por um `django.forms.Form` nem chamar `django.contrib.auth.password_validation.validate_password()`. Uma senha fraca (`123456`, igual ao nome de usuário, etc.) pode ser aceita na criação de conta por um `master`.

**Impacto**: só afeta criação de conta por um usuário já `master` — não é uma rota exposta a usuário anônimo. Ainda assim, reduz a garantia de que toda conta tem senha minimamente forte.

**Correção sugerida**: trocar a validação manual por um `ModelForm`/`Form` que chame `validate_password()`.

### `SystemLog.ip_address` sem retenção ou anonimização
`accounts/models.py:SystemLog` grava `ip_address` em todo evento de auditoria e nunca apaga ou anonimiza — não há job de retenção. Do ponto de vista de LGPD, IP é dado pessoal; guardá-lo indefinidamente sem justificativa de prazo é um risco de conformidade, mesmo sendo um log de auditoria legítimo (finalidade válida, mas sem prazo definido).

**Correção sugerida**: definir uma política de retenção (ex.: 6-12 meses) e um comando/cron que anonimize ou apague entradas mais antigas que o prazo.

## Decisões intencionais (não são gaps)

Para não confundir decisão deliberada com pendência:

- **Endpoints do kiosk (`/biometric/api/*`) são `csrf_exempt`**: intencional — autenticam via token de dispositivo, não cookie de sessão, então a proteção CSRF (contra credencial de cookie carregada automaticamente pelo navegador) não se aplica a essa rota. Não abre exceção para nenhuma outra view.
- **`unsafe-inline` no CSP**: mantido porque não há bundler de JS no projeto; revisar se isso mudar.
- **Template biométrico é reversível (não hash)**: necessário para a comparação 1:N nativa do SDK funcionar — a mitigação é a criptografia em repouso (Fernet), não hashing.
