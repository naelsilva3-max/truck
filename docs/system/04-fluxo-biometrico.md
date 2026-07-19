# Fluxo biométrico

## Dois modos de operação

1. **Máquina única** — o servidor Django tem o leitor ZK9500 conectado localmente (`python manage.py start_listener`). Simples, mas exige o leitor fisicamente no mesmo computador do servidor.
2. **Kiosk remoto** — uma máquina separada (portaria/recepção) roda `kiosk_agent.py`, autentica com um token de dispositivo e fala com o servidor por API. É o modo recomendado em produção (servidor num VPS sem hardware). Ver [Arquitetura do kiosk](05-arquitetura-kiosk.md).

Os dois modos usam o mesmo núcleo (`biometric/service.py`), então o comportamento de captura/identificação é idêntico — só muda onde o processo roda.

## Captura e enrolamento

`BiometricService.capture_registration()` pede **3 toques do mesmo dedo** (dedo levantado entre um toque e outro) e mescla as amostras com a chamada nativa `DBMerge` do SDK ZKFinger num único template de cadastro.

## Identificação (1:N)

`BiometricService.identify()` usa a comparação 1:N nativa do SDK (`DBIdentify`, score mínimo `DEFAULT_MIN_SCORE=50`). Só cai para comparação exata byte-a-byte quando o SDK/leitor não está disponível — usado pelo simulador (`BiometricSimulatorView`, **somente com `DEBUG=True`**) e pelos testes.

## Armazenamento

O template vai para `BiometricTemplate.template`, um `EncryptedBinaryField` (Fernet — ver [Modelo de dados](02-modelo-de-dados.md)). Não é um hash: a identificação 1:N precisa do template original, então a criptografia é reversível por design (não há alternativa que preserve a funcionalidade).

## Transporte

Kiosk → servidor: o template vai em base64 dentro de JSON, sobre HTTPS (`biometric/api_views.py:KioskEnrollView`). Sem camada extra de criptografia além do TLS + token de dispositivo no header `Authorization`.

## Sincronização com o kiosk

`KioskTemplateSyncView` (`GET /biometric/api/templates/`) devolve **todos os templates de funcionários ativos** (base64) para qualquer dispositivo autenticado — necessário para a comparação 1:N acontecer localmente no kiosk. Isso é uma superfície de exposição relevante se um token de dispositivo vazar: quem tiver o token consegue baixar todos os templates ativos. Mitigação atual: rotação de token é simples (`python manage.py kiosk_device revoke` + `create`), mas não há alerta automático de uso anômalo.

## Exclusão e retenção

- `EmployeeDeleteBiometricView` apaga fisicamente a linha de `BiometricTemplate` (não é soft-delete) e cancela qualquer `BiometricEnrollRequest` pendente.
- `BiometricTemplate.employee` é `on_delete=CASCADE` — apagar o funcionário apaga o template junto.
- `KioskTemplateSyncView` já filtra por `employee__is_active=True`, então **desativar** um funcionário o remove da próxima sincronização do kiosk, e o servidor rejeita com 409 no `/api/scan/` mesmo que o cache local do kiosk ainda o reconheça.
- Um funcionário que segue **ativo** mas teve só a biometria apagada **não tem essa segunda barreira** — o kiosk pode continuar reconhecendo-o localmente por até `KIOSK_TEMPLATE_REFRESH_SECONDS` (padrão 30s) até a próxima sincronização. Gap documentado em `docs/kiosk_deployment.md` §8.
