# Cadastro de funcionário

*Requer perfil Admin ou Master.*

## Cadastrar

1. Menu **Funcionários** → botão **+ Novo Funcionário**.
2. Preencha nome, cargo, dados de documento (RG/CPF, ou o documento de estrangeiro se marcar "Estrangeiro?"), endereço e telefone (opcionais).
3. Foto: use **Ligar Câmera** + **Capturar Foto** para tirar na hora, ou **Enviar Arquivo** para subir uma imagem já existente. **Trocar Foto** refaz a captura.
4. Clique em **Cadastrar**.

`[SCREENSHOT: tela de cadastro de funcionário com câmera aberta]`

## Editar

Na lista de **Funcionários**, clique em **Ver** no funcionário desejado, depois em **Editar**.

## Cadastrar biometria (digital)

Na página do funcionário, botão **Cadastrar Biometria**:

- Se o computador que você está usando **tem o leitor conectado**: siga as instruções na tela — passe o mesmo dedo 3 vezes, levantando o dedo entre uma passada e outra.
- Se o servidor **não tem leitor** (caso comum quando o sistema roda num servidor remoto): a tela muda para "Aguardando leitor do quiosque remoto..." e atualiza sozinha. Vá até a máquina do kiosk (portaria) e peça para a pessoa passar o dedo no leitor ali — o cadastro completa sozinho quando isso acontecer. Detalhes em [Uso do kiosk biométrico](07-kiosk-biometrico.md).
- Para cancelar um pedido que ficou esperando, clique em **Cancelar solicitação** na mesma tela.

`[SCREENSHOT: tela "Aguardando leitor do quiosque remoto..."]`

## Apagar biometria

Na tela de edição do funcionário, botão **Apagar Biometria** — usado quando a digital precisa ser recadastrada (dedo machucado, leitor trocado, etc.) ou quando o funcionário não deve mais bater ponto por digital. Isso não desativa o funcionário, só remove a digital cadastrada.

## Funcionário inativo

Não é possível apagar um funcionário — para removê-lo do dia a dia (sem perder o histórico de ponto/atribuição de caminhão), desmarque **Ativo?** na edição. Ele some das listas normais mas pode ser recuperado clicando em **Mostrar inativos** na lista de Funcionários.
