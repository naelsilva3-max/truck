# Arquitetura do kiosk

> Este é um resumo arquitetural. Para o passo a passo operacional completo (gerar token, instalar, rodar como serviço, rotacionar token, limitações conhecidas), o documento de referência é **[`docs/kiosk_deployment.md`](../kiosk_deployment.md)** — não duplicado aqui.

## O que é

`kiosk_agent.py` é um script Python **standalone** (zero import de Django/Postgres) que roda numa máquina separada do servidor, com o leitor ZK9500 conectado via USB. Reaproveita o mesmo núcleo de `biometric/service.py`, `listener.py`, `daemon.py` e `exceptions.py` — arquivos sem nenhuma dependência de Django, por isso "portáveis" para essa máquina.

Dois subcomandos:
- `kiosk_agent.py enroll --employee-id N` — cadastro de digital pontual
- `kiosk_agent.py listen` — reconhecimento contínuo (ponto) + ressincronização periódica de templates + polling de pedidos de cadastro remoto

## Autenticação

Só por **token de dispositivo** (`KioskDevice`, ver [Modelo de dados](02-modelo-de-dados.md)) — sem login de usuário. Configurado num `.env` local na máquina do kiosk (`KIOSK_SERVER_URL`, `KIOSK_DEVICE_TOKEN`, `KIOSK_DEVICE_ID`).

## Empacotamento

`kiosk_installer/` (fora da árvore de apps Django) empacota `kiosk_agent.py` com PyInstaller + um instalador gráfico Inno Setup, distribuível também pelo próprio site (`KioskInstallerListView`/`DownloadView`, acesso `master` apenas). O instalador não é assinado digitalmente — SmartScreen/Smart App Control do Windows pode bloquear a primeira execução (detalhe e contorno em `docs/kiosk_deployment.md` §3).

## Limitações conhecidas (v1)

Resumo — lista completa em `docs/kiosk_deployment.md` §8:
- Sem fila offline (evento é descartado se a conexão cair no momento do toque)
- Cache local do kiosk pode ficar até 30s desatualizado
- Gestão de token só por linha de comando, sem tela administrativa
- Pedidos de cadastro remoto não expiram sozinhos
- Não há coordenação para múltiplos kiosks físicos simultâneos
