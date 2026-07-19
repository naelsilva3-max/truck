# Testes

## Como rodar

```
pytest
```

A partir da raiz do repo. `conftest.py` tem uma fixture `autouse` que redireciona `MEDIA_ROOT` para uma pasta temporária — os testes nunca tocam em arquivos de mídia reais.

Para reproduzir exatamente uma falha de teste baseado em propriedades (Hypothesis), use o seed que ele reporta:
```
pytest --hypothesis-seed=<seed-reportado-na-falha>
```

## Organização

Testes ficam em pacotes `tests/` por app (padrão pytest + `pytest-django`).

| App | Cobertura |
|---|---|
| `attendance/tests/` | Máquina de estados do ponto, tratamento de leitura duplicada, views |
| `biometric/tests/` | Backend de hardware (abstração), ciclo de vida do listener/reconexão, models, API do kiosk, autenticação por token (incluindo o throttle) |
| `employees/tests/` | Models, forms, renderização de forms, views |
| `trucks/tests/` | Models, integração, propriedades (Hypothesis), contagem de query (guarda contra N+1), upload de foto, live poll |
| `employee_truck_control/tests/` | Middlewares customizados, `ProtectedMediaView`, rate limiting, validators, índice de relatórios |
| `accounts/tests.py` | Autenticação, gestão de usuário |
| `visitors/tests.py` | CRUD de visitante e visita, controle de acesso, live poll/update |

## Testes de propriedades (Hypothesis)

`trucks/tests/test_properties.py` é o arquivo mais sensível a mudanças de model — usa geração aleatória de dados para achar casos de borda que exemplos fixos não cobririam. Ao adicionar um `CharField`/`TextField` de texto livre em qualquer model, use `ProhibitNullCharactersValidator` (ver [Modelo de dados](02-modelo-de-dados.md)) e, se fizer sentido, uma estratégia (`st.text(...)`) correspondente aqui — `models.CharField` não bloqueia o caractere NUL por padrão como `forms.CharField` bloqueia.

## Exemplos de teste "guarda de regressão" para comportamento sensível

- `trucks/tests/test_list_query_count.py` — trava o número de queries da listagem (guarda contra N+1)
- `employee_truck_control/tests/test_rate_limit.py` — trava o comportamento de bloqueio por tentativas de login
- `employee_truck_control/tests/test_protected_media.py` — trava que mídia exige autenticação
