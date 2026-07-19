# Uso do kiosk biométrico

Esta página é para quem **usa** o leitor de digital no dia a dia (portaria/recepção). Para instalar ou configurar o kiosk pela primeira vez, isso é trabalho técnico — veja `docs/kiosk_deployment.md` ou peça para quem administra o sistema.

## Bater o ponto

Simples: **passe o dedo cadastrado no leitor**. Uma luz/som (dependendo do leitor) confirma a leitura. O sistema identifica automaticamente quem é e registra a etapa certa do dia (Entrada, Saída Almoço, Retorno Almoço ou Saída) — não precisa escolher nada na tela.

Se o dedo não for reconhecido:
- Confira se é o mesmo dedo cadastrado.
- Limpe o leitor e o dedo (poeira/umidade atrapalham a leitura).
- Se a pessoa foi cadastrada há poucos segundos, pode levar até ~30 segundos para o kiosk "aprender" a nova digital — tente de novo em instantes.
- Persistindo, procure um `admin`/`master` para verificar o cadastro dela no sistema.

## Cadastrar uma digital pelo kiosk

Duas formas:

1. **Pedido feito pelo site**: um `admin` clica em **Cadastrar Biometria** na página do funcionário (ver [Cadastro de funcionário](03-cadastro-funcionario.md)) — o kiosk detecta o pedido sozinho em poucos segundos e pede 3 toques do dedo automaticamente. Nada precisa ser digitado na máquina do kiosk.
2. **Comando direto na máquina do kiosk** (uso técnico, geralmente feito por quem administra o sistema):
   ```
   python kiosk_agent.py enroll --employee-id <id-do-funcionario>
   ```

Em ambos os casos: passe o **mesmo dedo 3 vezes**, levantando entre uma passada e outra.

## O kiosk "travou" ou parece offline

O programa do kiosk deve ficar sempre rodando em segundo plano naquela máquina (inicia sozinho com o Windows). Se parar de reconhecer todo mundo (não só uma pessoa):

1. Verifique se a máquina do kiosk tem internet/rede até o servidor.
2. Verifique se o leitor USB está bem conectado.
3. Se nada resolver, reinicie a máquina do kiosk — o serviço volta a subir sozinho.
4. Persistindo, acione o suporte técnico.

Enquanto o kiosk está offline, **nenhum ponto é registrado** — não existe fila para reenviar depois. Batidas de ponto durante o período offline se perdem.
