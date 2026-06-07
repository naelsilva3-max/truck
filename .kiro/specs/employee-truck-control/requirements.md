# Requirements Document

## Introduction

Este documento descreve os requisitos funcionais e não-funcionais do sistema **Employee & Truck Control**: uma aplicação web Django/Python para controle de ponto de funcionários via biometria digital (leitor ZKTeco ZK9500) e gestão de frota de caminhões com associação de motoristas.

Os funcionários são entidades gerenciadas pelo sistema — não possuem login ou senha próprios. O acesso administrativo à interface web é feito por usuários do Django Admin. O sistema garante conformidade com a LGPD para dados biométricos e mantém logs imutáveis de ponto e associações.

---

## Glossary

- **System**: O sistema web Django Employee & Truck Control.
- **Employee**: Entidade cadastrada no sistema representando um funcionário da empresa. Não possui credenciais de acesso ao sistema.
- **Admin**: Usuário autenticado no Django Admin com permissão de gerenciar funcionários, caminhões e associações.
- **BiometricService**: Componente de software responsável pela comunicação com o leitor biométrico ZKTeco ZK9500.
- **BiometricTemplate**: Registro binário que armazena o template da impressão digital de um funcionário.
- **BiometricListener**: Processo em background que monitora eventos do leitor biométrico e aciona o registro de ponto.
- **AttendanceRecord**: Registro de ponto de um funcionário, contendo horário de entrada e, opcionalmente, horário de saída.
- **Truck**: Entidade que representa um caminhão da frota, identificado por placa e chassi únicos.
- **TruckAssignment**: Associação entre um motorista (Employee com `is_driver=True`) e um caminhão, com período de vigência.
- **Driver**: Funcionário com o atributo `is_driver=True`, habilitado a ser associado a um caminhão.
- **EmployeeManager**: Componente responsável pelo CRUD de funcionários e gerenciamento de templates biométricos.
- **TruckManager**: Componente responsável pelo CRUD de caminhões e gerenciamento de associações motorista–caminhão.
- **AttendanceService**: Componente responsável por criar, atualizar e consultar registros de ponto.
- **ZKTeco ZK9500**: Leitor biométrico de impressão digital conectado via USB ou TCP/IP.

---

## Requirements

### Requirement 1: Cadastro de Funcionários

**User Story:** Como Admin, quero cadastrar e gerenciar funcionários no sistema, para que eu possa manter o registro atualizado do quadro de pessoal da empresa.

#### Acceptance Criteria

1. THE EmployeeManager SHALL permitir criar um funcionário com os campos obrigatórios `name`, `role` e `hire_date`, e os campos opcionais `department`, `phone`, indicador de motorista e status ativo.
2. WHEN um Admin submete o formulário de criação de funcionário com `name` vazio, THE System SHALL rejeitar a submissão e exibir mensagem de validação indicando que o nome é obrigatório.
3. WHEN um Admin submete o formulário de criação de funcionário com `hire_date` posterior à data atual, THE System SHALL rejeitar a submissão e exibir mensagem de validação indicando que a data de admissão não pode ser futura.
4. THE EmployeeManager SHALL permitir listar todos os funcionários cadastrados.
5. WHEN um Admin solicita os dados de um funcionário por identificador único, THE EmployeeManager SHALL retornar os dados do funcionário correspondente; IF o identificador não existir, THEN THE System SHALL retornar HTTP 404 ou exibir mensagem de erro indicando que o funcionário não foi encontrado.
6. WHEN um Admin solicita a atualização de um funcionário por identificador único, THE EmployeeManager SHALL atualizar os dados do funcionário correspondente; IF o identificador não existir, THEN THE System SHALL retornar HTTP 404 ou exibir mensagem de erro indicando que o funcionário não foi encontrado.
7. WHEN um Admin desativa um funcionário (define `is_active=False`), THE System SHALL preservar todos os registros de ponto e associações anteriores desse funcionário.
8a. WHEN um Admin solicita a exclusão de um funcionário que possui biometria cadastrada, THE System SHALL exibir um diálogo de confirmação mostrando o nome do funcionário e as informações do template biométrico associado.
8b. WHEN o Admin confirma a exclusão no diálogo de confirmação, THE System SHALL remover o funcionário e o BiometricTemplate associado do banco de dados.
8c. WHEN o Admin cancela a exclusão no diálogo de confirmação, THE System SHALL abortar a operação e preservar os dados do funcionário e do BiometricTemplate sem alterações.

---

### Requirement 2: Cadastro e Gerenciamento de Templates Biométricos

**User Story:** Como Admin, quero cadastrar a impressão digital de cada funcionário, para que o sistema possa identificá-lo automaticamente no leitor biométrico.

#### Acceptance Criteria

1. WHEN um Admin inicia o cadastro biométrico de um funcionário, THE BiometricService SHALL solicitar a captura da impressão digital ao leitor ZKTeco ZK9500.
2. WHEN o ZKTeco ZK9500 retorna um template biométrico válido (tamanho maior que zero e não superior a 10 KB), THE System SHALL armazenar o template no banco de dados vinculado ao funcionário e exibir mensagem de confirmação de sucesso ao Admin.
3. IF o template biométrico capturado possui tamanho igual a zero bytes OU supera o tamanho máximo de 10 KB, THEN THE System SHALL rejeitar o armazenamento e informar o Admin sobre o erro de captura.
4. THE System SHALL garantir que cada funcionário possua exatamente um BiometricTemplate armazenado (relação OneToOne), sem estado inativo — ao recadastrar, o template anterior é substituído imediatamente.
5. WHEN um Admin recadastra a biometria de um funcionário que já possui template, THE System SHALL substituir o template anterior pelo novo.
6. THE System SHALL armazenar templates biométricos exclusivamente como dados binários no banco de dados, sem expô-los como arquivos acessíveis por URL.
7. IF o BiometricService não conseguir conectar ao ZKTeco ZK9500 ou se a captura expirar durante o processo de cadastro biométrico, THEN THE System SHALL exibir mensagem de erro ao Admin e não persistir nenhum template no banco de dados.

---

### Requirement 3: Identificação Biométrica e Registro de Ponto

**User Story:** Como funcionário, quero registrar minha entrada e saída apenas aproximando meu dedo do leitor biométrico, para que o controle de ponto seja automático e sem necessidade de cartões ou senhas.

#### Acceptance Criteria

1. WHILE o BiometricListener está em execução, THE System SHALL monitorar continuamente o leitor ZKTeco ZK9500 em busca de eventos de captura de impressão digital.
2. WHEN o BiometricListener recebe um evento de digital capturada, THE BiometricService SHALL comparar o template capturado com todos os templates armazenados (identificação 1:N) utilizando um limiar mínimo de pontuação; IF a pontuação do melhor candidato for inferior ao limiar mínimo, THEN THE BiometricService SHALL tratar a digital como não reconhecida e retornar `None`.
3. WHEN um funcionário é identificado e não possui `AttendanceRecord` em aberto (sem `exit_time`), THE AttendanceService SHALL criar um novo `AttendanceRecord` com `entry_time` igual ao momento atual.
4. WHEN um funcionário é identificado e já possui um `AttendanceRecord` em aberto (com `entry_time` e sem `exit_time`), THE AttendanceService SHALL atualizar esse registro definindo `exit_time` igual ao momento atual.
5. THE AttendanceService SHALL garantir que cada funcionário possua no máximo um `AttendanceRecord` em aberto por vez.
6. THE System SHALL garantir que o `exit_time` de qualquer `AttendanceRecord` seja sempre posterior ao `entry_time` em pelo menos 1 segundo.
7. IF o template capturado não corresponder a nenhum funcionário cadastrado, THEN THE BiometricService SHALL retornar `None` e o BiometricListener SHALL registrar o evento como "digital desconhecida" no log do sistema.
8. WHEN um evento biométrico é processado com sucesso, THE System SHALL emitir feedback sonoro e/ou visual no leitor ZKTeco ZK9500.
9. IF o feedback de uma digital desconhecida é emitido, THEN THE System SHALL utilizar sinal diferenciado (beep ou LED) em relação ao feedback de identificação bem-sucedida.
10. IF o ZKTeco ZK9500 ficar indisponível durante a operação do listener, THEN THE System SHALL registrar o erro de hardware no log e tentar reconexão sem encerrar o BiometricListener.
11. IF a persistência de um AttendanceRecord falhar devido a erro de banco de dados, THEN THE System SHALL registrar o erro no log e emitir sinal de erro no leitor ZKTeco ZK9500.

---

### Requirement 4: Listener Biométrico em Background

**User Story:** Como Admin, quero que o sistema processe eventos biométricos continuamente em segundo plano, para que os registros de ponto ocorram sem intervenção manual.

#### Acceptance Criteria

1. THE BiometricService SHALL executar o BiometricListener em thread ou processo separado, sem bloquear o servidor web Django.
2. THE BiometricService SHALL expor métodos `start_listener` e `stop_listener` para iniciar e encerrar o monitoramento em background.
3. WHEN `start_listener` é invocado, THE BiometricService SHALL registrar o callback de processamento de eventos biométricos antes de iniciar o monitoramento, garantindo que nenhum evento seja perdido após o início.
4. IF o BiometricListener encontrar uma exceção durante o processamento de um evento, THEN THE System SHALL registrar o erro no log com stack trace completo e retomar o monitoramento sem encerrar o processo.

---

### Requirement 5: Conexão com o Leitor Biométrico

**User Story:** Como Admin, quero que o sistema se conecte ao leitor ZKTeco ZK9500 via USB ou TCP/IP, para que a comunicação com o hardware seja estabelecida de forma confiável.

#### Acceptance Criteria

1. THE BiometricService SHALL oferecer métodos `connect` e `disconnect` para gerenciar a conexão com o leitor ZKTeco ZK9500; o método `connect` SHALL aceitar como parâmetro um identificador de dispositivo USB ou um par host+porta TCP/IP.
2. WHEN `connect` é invocado e o dispositivo ZKTeco ZK9500 não é encontrado ou não está acessível, THE BiometricService SHALL lançar `BiometricDeviceNotFoundError`.
3a. IF `BiometricDeviceNotFoundError` é lançado, THEN THE System SHALL exibir mensagem de erro amigável ao Admin na interface web.
3b. IF `BiometricDeviceNotFoundError` é lançado, THEN THE System SHALL registrar o evento no log do sistema com timestamp e detalhes do erro.
4. WHEN `connect` é invocado e o dispositivo é encontrado, THE BiometricService SHALL retornar `True` indicando conexão bem-sucedida.
5. WHEN `disconnect` é invocado, THE BiometricService SHALL encerrar a conexão com o leitor de forma segura, liberando recursos de hardware; após o disconnect, qualquer tentativa de captura ou identificação SHALL lançar erro de conexão.
6. WHEN `disconnect` é invocado e não existe conexão ativa, THE BiometricService SHALL retornar sem erro (operação no-op).

---

### Requirement 6: Cadastro e Gerenciamento de Caminhões

**User Story:** Como Admin, quero cadastrar e gerenciar os caminhões da frota, para que eu tenha controle completo sobre os veículos disponíveis na empresa.

#### Acceptance Criteria

1. THE TruckManager SHALL permitir criar um caminhão com os campos: placa, modelo, cor, chassi, ano e status; o campo `status` SHALL aceitar exclusivamente os valores `'ativo'` ou `'inativo'`; o campo `year`, quando informado, SHALL ser um valor inteiro entre 1900 e o ano corrente inclusive.
2. THE System SHALL exigir que `model` (até 100 caracteres) e `color` (até 50 caracteres) sejam informados e não estejam vazios na criação de um caminhão.
3. WHEN um Admin tenta criar um caminhão com `license_plate` já existente no banco de dados, THE System SHALL rejeitar a operação e exibir mensagem de validação indicando placa duplicada.
4. WHEN um Admin tenta criar um caminhão com `chassis` já existente no banco de dados, THE System SHALL rejeitar a operação e exibir mensagem de validação indicando chassi duplicado.
5. THE System SHALL validar que `license_plate` segue o formato alfanumérico válido (ex.: padrão Mercosul `AAA0A00` ou padrão antigo `AAA0000`).
6. THE System SHALL validar que `chassis` possui exatamente 17 caracteres alfanuméricos (padrão VIN).
7. THE TruckManager SHALL permitir listar todos os caminhões cadastrados.
8. WHEN um Admin solicita os dados de um caminhão por identificador único, THE TruckManager SHALL retornar os dados do caminhão correspondente; IF o identificador não existir, THEN THE System SHALL retornar HTTP 404 ou exibir mensagem de erro indicando que o caminhão não foi encontrado.
9. WHEN um Admin solicita a atualização de um caminhão por identificador único, THE TruckManager SHALL atualizar os campos `model`, `color`, `year` e `status` do caminhão correspondente, revalidando a unicidade de `license_plate` e `chassis` caso sejam alterados; IF o identificador não existir, THEN THE System SHALL retornar HTTP 404 ou exibir mensagem de erro indicando que o caminhão não foi encontrado.

---

### Requirement 7: Associação de Motorista a Caminhão

**User Story:** Como Admin, quero associar e desassociar motoristas a caminhões, para que eu possa controlar qual funcionário está responsável por qual veículo.

#### Acceptance Criteria

1. WHEN um Admin tenta associar um funcionário que não possui `is_driver=True` a um caminhão, THE System SHALL rejeitar a operação e exibir mensagem de validação indicando que o funcionário não é motorista.
2. WHEN um Admin tenta criar uma `TruckAssignment` para um caminhão que já possui associação ativa (`unassigned_at=None`), THE System SHALL rejeitar a operação e exibir mensagem de validação indicando que o caminhão já possui motorista ativo.
3. WHEN um Admin cria uma `TruckAssignment` válida, THE System SHALL registrar `assigned_at` com o timestamp UTC do momento atual e manter `unassigned_at` como `null`.
4. WHEN um Admin encerra uma `TruckAssignment` ativa, THE System SHALL definir `unassigned_at` com o timestamp UTC do momento atual, tornando a associação inativa.
5. THE System SHALL garantir que, para qualquer caminhão, no máximo uma `TruckAssignment` possua `unassigned_at=None` em qualquer momento.
6. THE System SHALL garantir que `assigned_at` não seja posterior a `unassigned_at` em nenhuma `TruckAssignment`.
7. WHEN um Admin solicita o motorista atualmente associado a um caminhão, THE TruckManager SHALL retornar o Driver da `TruckAssignment` ativa, ou `None` se não houver associação ativa.
8. WHEN um Admin solicita o histórico de associações de um caminhão, THE TruckManager SHALL retornar todas as `TruckAssignment` do caminhão ordenadas da mais recente para a mais antiga.
9. WHEN um Admin tenta encerrar uma `TruckAssignment` que já está inativa (`unassigned_at` não é `null`), THE System SHALL rejeitar a operação e exibir mensagem de validação indicando que a associação já está encerrada.

---

### Requirement 8: Consulta de Registros de Ponto

**User Story:** Como Admin, quero consultar o histórico de registros de ponto dos funcionários, para que eu possa auditar presenças e ausências.

#### Acceptance Criteria

1. THE AttendanceService SHALL listar todos os `AttendanceRecord`s de um funcionário, ordenados do mais recente para o mais antigo.
2. WHEN um Admin consulta registros de ponto informando um intervalo de datas (`start_date`, `end_date`), THE System SHALL retornar somente os registros cujo `date` esteja dentro do intervalo inclusive; IF nenhum registro corresponder ao filtro, THEN THE System SHALL retornar lista vazia.
3. THE AttendanceService SHALL retornar o `AttendanceRecord` em aberto de um funcionário, ou `None` se não houver registro em aberto.
4. WHEN um Admin visualiza uma lista de `AttendanceRecord`, THE System SHALL exibir `entry_time`, `exit_time` (omitido quando `null`) e `date` para cada registro.
5. IF um Admin consulta registros de ponto de um funcionário cujo identificador não existe, THEN THE System SHALL retornar resposta de erro indicando que o funcionário não foi encontrado.

---

### Requirement 9: Segurança e Controle de Acesso

**User Story:** Como Admin, quero que o acesso à interface web seja protegido por autenticação, para que somente usuários autorizados possam gerenciar os dados do sistema.

#### Acceptance Criteria

1. THE System SHALL exigir autenticação Django (`login_required`) em todas as views da interface web; WHEN uma requisição não autenticada é feita a qualquer view protegida, THE System SHALL redirecionar para a página de login.
2. THE System SHALL utilizar o sistema de autenticação padrão do Django Admin para controle de acesso administrativo.
3. THE System SHALL armazenar templates biométricos somente como dados binários no banco de dados, sem expô-los via URL ou sistema de arquivos acessível externamente.
4. IF uma operação destrutiva sobre dados de funcionário com biometria é solicitada, THEN THE System SHALL exigir confirmação explícita do Admin.
5. WHEN uma exclusão física de `AttendanceRecord` ou `TruckAssignment` é tentada via interface web, THE System SHALL rejeitar a requisição e retornar resposta de erro sem modificar o banco de dados.

---

### Requirement 10: Conformidade com LGPD para Dados Biométricos

**User Story:** Como empresa, quero que o tratamento de dados biométricos dos funcionários esteja em conformidade com a LGPD, para que a empresa cumpra as obrigações legais de proteção de dados pessoais sensíveis.

#### Acceptance Criteria

1. THE System SHALL tratar templates biométricos como dados pessoais sensíveis e não expor dados de BiometricTemplate em respostas de API, arquivos de log ou integrações externas.
2. IF um funcionário é excluído do sistema, THEN THE System SHALL remover ou anonimizar o `BiometricTemplate` associado em até 30 dias corridos após a exclusão confirmada; IF o processo de remoção ou anonimização falhar, THEN THE System SHALL registrar a falha no log e alertar o Admin.
3. WHEN qualquer view ou template Django tenta acessar diretamente um objeto `BiometricTemplate`, THE System SHALL lançar exceção de controle de acesso ou mecanismo equivalente de restrição.

---

### Requirement 11: Integridade e Imutabilidade de Logs

**User Story:** Como Admin, quero que os registros de ponto e histórico de associações sejam imutáveis, para que o sistema mantenha um log de auditoria confiável.

#### Acceptance Criteria

1. WHEN uma exclusão física de `AttendanceRecord` é tentada via interface web ou API, THE System SHALL rejeitar a requisição com resposta de erro e preservar o registro sem alterações.
2. WHEN uma exclusão física de `TruckAssignment` é tentada via interface web ou API, THE System SHALL rejeitar a requisição com resposta de erro e preservar o registro sem alterações.
3. WHEN a desativação de um funcionário ou caminhão é realizada, THE System SHALL utilizar soft-delete (definir `is_active=False`) em vez de exclusão física.
4. THE System SHALL preservar, para cada `TruckAssignment`, os seguintes dados indefinidamente: identificador do caminhão, identificador do motorista, timestamp `assigned_at`, timestamp `unassigned_at` (quando definido) e campo `notes`.
