# Manual do usuário

Guia de uso do dia a dia do sistema — para quem cadastra funcionários, gerencia visitantes, caminhões e acompanha o ponto. Não é um manual técnico; para arquitetura e operação de servidor, veja [`docs/system/`](../system/README.md).

## Quem usa o quê

| Perfil (role no sistema) | O que consegue fazer |
|---|---|
| **Leitura** (`simple`) | Ver listagens, detalhes, relatórios em PDF — não cria nem edita nada |
| **Admin** (`admin`) | Tudo da Leitura + cadastrar/editar funcionário, visitante, caminhão, motorista |
| **Master** (`master`) | Tudo do Admin + gerenciar usuários do sistema, ver o log de auditoria, revisar pontos pendentes, gerar token/instalador de kiosk |

Se um botão não aparece pra você, é porque seu perfil não tem permissão para aquela ação — fale com um usuário `master` da sua empresa para solicitar acesso.

## Índice

1. [Introdução](01-introducao.md)
2. [Login](02-login.md)
3. [Cadastro de funcionário](03-cadastro-funcionario.md)
4. [Registro de ponto](04-registro-ponto.md)
5. [Visitantes](05-visitantes.md)
6. [Caminhões](06-caminhoes.md)
7. [Uso do kiosk biométrico](07-kiosk-biometrico.md)
8. [Erros comuns](08-erros-comuns.md)
9. [Privacidade dos seus dados](09-privacidade-dados.md)
