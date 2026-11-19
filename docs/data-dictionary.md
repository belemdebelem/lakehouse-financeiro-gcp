# Dicionário inicial de dados

Os dados são sintéticos e reproduzíveis. Identificadores são técnicos,
sem relação com pessoas ou operações reais. Arquivos de entrada são CSV
UTF-8 com cabeçalhos `snake_case`, datas `YYYY-MM-DD` e decimais com
ponto.

## Contrato de arquivos implementado (Fase 2)

- Gerador: `src/lakehouse/generation.py`, seed padrão `20261117`, 10
  clientes, 1 a 2 contratos por cliente e 6 parcelas por contrato.
- Data de referência para status das parcelas: `2026-01-31`. Quando uma
  parcela é paga antecipadamente, `paid_at` não ultrapassa essa data.
- Arquivos válidos: `data/sample/customers.csv`, `contracts.csv` e
  `installments.csv`, regeneráveis com
  `uv run python -m lakehouse.generation`.
- Esquema e ordem das colunas: `src/lakehouse/schema.py` (`FIELDS`).
  O único campo que pode ficar vazio é `installments.paid_at`.
- Timestamps usam `YYYY-MM-DDTHH:MM:SSZ` em UTC; valores monetários têm
  duas casas e a taxa anual, quatro.
- Validação estrutural: `validate_dataset` verifica cabeçalho, campos
  obrigatórios, domínios, chaves únicas, relacionamentos e coerência
  básica de datas e valores.
- Exemplos inválidos em `data/sample/invalid/`: `customer_id` duplicado,
  domínios inválidos, contrato sem cliente, parcela sem contrato,
  `end_date` anterior a `start_date` e `amount_paid` maior que
  `amount_due`.
- Regras analíticas e testes do dbt foram implementados na Fase 6. Na
  Fase 7, `store_failures`, `source freshness` e `ops.dq_results` passaram
  a ser persistentes e rastreáveis. A validação Python da Fase 2 continua
  sendo apenas estrutural.

## `customers` — clientes fictícios

**Granularidade:** uma linha por cliente.

**Chave:** `customer_id`.

| Campo | Tipo lógico | Regra |
|---|---|---|
| `customer_id` | STRING | Obrigatório, único e estável entre lotes. Identificador sintético. |
| `customer_segment` | STRING | Obrigatório; domínio inicial: `mass`, `affluent`, `business`. |
| `created_at` | DATE | Obrigatório; data fictícia de criação. |
| `updated_at` | TIMESTAMP | Obrigatório em UTC; maior ou igual a `created_at`, usado para incrementalidade e desempate. |

## `contracts` — contratos de crédito

**Granularidade:** uma linha por contrato.

**Chave:** `contract_id`. `customer_id` referencia `customers.customer_id`.

| Campo | Tipo lógico | Regra |
|---|---|---|
| `contract_id` | STRING | Obrigatório, único e estável. |
| `customer_id` | STRING | Obrigatório; deve existir em `customers`. |
| `product_type` | STRING | Obrigatório; domínio inicial: `personal_loan`, `auto_loan`. |
| `principal_amount` | NUMERIC | Obrigatório e maior que zero; valor sintético. |
| `annual_interest_rate` | NUMERIC | Obrigatório; taxa anual decimal entre 0 e 1 (ex.: 0.15 = 15% a.a.); limites validados no gerador. |
| `start_date` | DATE | Obrigatório. |
| `end_date` | DATE | Obrigatório e posterior a `start_date`. |
| `status` | STRING | Obrigatório; `active`, `closed` ou `cancelled`. |
| `updated_at` | TIMESTAMP | Obrigatório em UTC; usado como marcador de alteração incremental. |

## `installments` — parcelas e pagamentos

**Granularidade:** uma linha por parcela contratual; pagamentos parciais
não fazem parte do MVP.

**Chave de negócio:** (`contract_id`, `installment_number`).
`contract_id` referencia `contracts.contract_id`.

| Campo | Tipo lógico | Regra |
|---|---|---|
| `contract_id` | STRING | Obrigatório; deve existir em `contracts`. |
| `installment_number` | INT64 | Obrigatório e maior que zero; único dentro do contrato. |
| `due_date` | DATE | Obrigatório. |
| `paid_at` | DATE | Nulo enquanto não pago; se informado, não pode anteceder a origem do contrato. |
| `amount_due` | NUMERIC | Obrigatório e maior que zero. |
| `amount_paid` | NUMERIC | Zero ou igual a `amount_due` no MVP; pagamentos parciais ficam fora desta versão. |
| `status` | STRING | `open`, `paid` ou `overdue`; Silver recalcula/valida conforme datas e valores. |
| `updated_at` | TIMESTAMP | Obrigatório em UTC; usado como marcador de alteração incremental. |

## Metadados de ingestão

Adicionados na Bronze e/ou na tabela `ops`, não exigidos nos arquivos de
origem:

| Campo | Tipo lógico | Uso |
|---|---|---|
| `batch_id` | STRING | Identidade estável derivada da entidade e do checksum SHA-256 do conteúdo. Reenvio idêntico reutiliza o mesmo identificador, independentemente do caminho no GCS. |
| `source_file` | STRING | Caminho/nome do objeto de origem no GCS. |
| `ingested_at` | TIMESTAMP | Instante UTC da ingestão. |
| `record_checksum` | STRING | Opcional; SHA-256 da linha canônica quando necessário à deduplicação. |
| `pipeline_version` | STRING | Opcional; versão do código (ex.: git SHA) que produziu o lote. |

## Caminho e metadados no GCS (Fase 4)

Os CSVs sintéticos são enviados para:

`landing/<entidade>/ingestion_date=YYYY-MM-DD/<arquivo>`

Cada objeto recebe `batch_id`, `sha256`, `source_file` com o caminho do
próprio objeto, `ingestion_date`, `ingested_at` em UTC e `row_count`. O
`batch_id` é estável por entidade e checksum, conforme a tabela acima.

A precondição `if_generation_match=0` impede substituição silenciosa. Um
reenvio idêntico falha com `ObjectAlreadyExistsError` e o objeto original
permanece intacto; a data de ingestão faz parte do caminho, não do
conteúdo do arquivo.

## Tabelas Bronze e `ops` (Fase 5)

O DDL versionado em `sql/bronze/tables.sql`,
`sql/bronze/staging_tables.sql` e `sql/ops/ingestion_batches.sql` é a
única fonte de verdade dos schemas. Datasets, bucket e IAM permanecem no
Terraform.

- `bronze.customers`, `bronze.contracts` e `bronze.installments` usam as
  colunas de origem descritas acima mais `batch_id`, `source_file`,
  `ingested_at` e `ingestion_date`.
- Chaves de `MERGE`: `customer_id`; `contract_id`; e
  (`contract_id`, `installment_number`).
- Tabelas finais são particionadas por `ingestion_date`. Clustering:
  `customer_segment` em `customers`; `product_type` e `status` em
  `contracts`; `status` em `installments`.
- Tabelas `<entidade>_staging` contêm somente as colunas de origem, com
  schema explícito; cada carga usa `WRITE_TRUNCATE` na staging.
- `ops.ingestion_batches` registra por lote: `batch_id`, `entity`,
  `source_file`, `row_count`, `status`, `error`, `started_at`,
  `finished_at` e `ingestion_date`. Status possíveis: `STARTED`,
  `SUCCEEDED` e `FAILED`. A chave lógica é (`batch_id`, `entity`).

O lote de `2026-11-17` carregou 10 clientes, 13 contratos e 78 parcelas;
as três entradas em `ops.ingestion_batches` estão `SUCCEEDED`.

## Modelos Silver e Gold (Fase 6)

Projetos dbt ficam em `dbt/`. O target `prod` grava em `silver` e `gold`;
outros targets, como `dev`, gravam em `silver_dev` e `gold_dev` pela macro
`generate_schema_name`. A data de referência padrão é `2026-01-31`,
configurada em `vars.as_of_date`.

| Modelo | Camada | Granularidade / regra principal |
|---|---|---|
| `silver_customers` | Silver | Uma linha por `customer_id`; `customer_segment` em minúsculas, deduplicação por `updated_at`, `ingested_at` e `source_file`. |
| `silver_contracts` | Silver | Uma linha por `contract_id`; `product_type` e `status` normalizados; deduplicação determinística. |
| `silver_installments` | Silver | Uma linha por (`contract_id`, `installment_number`); `status` normalizado e deduplicação determinística. |
| `mart_carteira_credito` | Gold | (`reference_month`, `product_type`): principal original somado de contratos `active`/`closed` cujo intervalo cobre o fim do mês. |
| `mart_inadimplencia` | Gold | (`due_month`, `product_type`): parcelas com vencimento anterior à data de referência, sem pagamento integral até essa data e status `open`/`overdue`. |
| `fato_pagamentos` | Gold | (`contract_id`, `installment_number`): pagamentos com `paid_at` preenchido, com mês de pagamento e dias até/atraso em relação ao vencimento. |

Modelos Silver são incrementais com `merge`, partição por `updated_at`,
clustering e janela de segurança de 3 dias para dados atrasados. Contratos
de modelo são enforcement apenas na Silver, com `on_schema_change: fail`.
Modelos Gold são tabelas recreáveis.

O build em `dev` produziu: `silver_customers` 10, `silver_contracts` 13,
`silver_installments` 78, `mart_carteira_credito` 38,
`mart_inadimplencia` 13 e `fato_pagamentos` 61 linhas. A reexecução do
mesmo lote manteve essas contagens.

## Qualidade, auditoria e recuperação (Fase 7)

### `bronze_dbt_test__audit`

Dataset criado pelo Terraform e usado pelo dbt quando
`data_tests.+store_failures: true`. Cada teste com falha grava uma tabela
com seu nome; uma execução sem falhas deixa as tabelas vazias. A macro
`generate_schema_name` preserva o nome do schema para testes, sem sufixo
`_dev`. Após o `dbt test` final, o dataset continha 77 tabelas de auditoria.

### `dbt/target/sources.json`

Artefato de `dbt source freshness`. O campo `results[]` traz `status` e
`max_loaded_at_time_ago_in_s` por fonte. Os limiares configurados em
`bronze.*.ingested_at` são `warn_after=72h` e `error_after=168h`. Na
validação final, as três fontes ficaram `PASS`, com maior idade de
`45.5` horas.

### `ops.dq_results`

Tabela operacional criada por `sql/ops/dq_results.sql`, particionada por
`ingestion_date` e clusterizada por `entity` e `metric_name`.

| Campo | Tipo lógico | Regra |
|---|---|---|
| `ingestion_date` | DATE | Data do lote analisado; chave e partição. |
| `entity` | STRING | `customers`, `contracts`, `installments`, `dbt` ou `bronze`. |
| `batch_id` | STRING | Identidade do lote para entidades; `invocation_id` do dbt para métricas de teste/freshness. |
| `metric_name` | STRING | Métrica registrada; vence com `ingestion_date` e `entity`. |
| `metric_value` | NUMERIC | Valor da métrica, convertido de texto pelo módulo de qualidade. |
| `status` | STRING | `PASS`, `WARN` ou `FAIL`. |
| `details` | STRING | JSON com metadados da métrica, como `batch_id`, `invocation_id` e limiares de freshness. |
| `checked_at` | TIMESTAMP | Instante UTC da verificação. |

As métricas por entidade são `input_count`, `output_count` e
`rejected_count`. As métricas globais são `dbt_tests_passed`,
`dbt_tests_failed` e `source_freshness_max_age_hours`. O módulo
`src/lakehouse/quality.py` conta Bronze e Silver do target ativo, lê os
artefatos do dbt e grava 12 linhas com `load_table_from_json` no decorador
de partição e `WRITE_TRUNCATE`. Reexecutar para a mesma data substitui a
partição. A validação final registrou 12 linhas `PASS` para `2026-11-17`,
com `10/10`, `13/13` e `78/78` linhas de entrada/saída, zero rejeitados,
77 testes aprovados e zero falhas.

## Mapeamento para dbt

| Bronze (source) | Modelo Silver | Uso principal |
|---|---|---|
| `bronze.customers` | `silver_customers` | Base de cliente e segmento. |
| `bronze.contracts` | `silver_contracts` | Carteira, produto, status e datas. |
| `bronze.installments` | `silver_installments` | Inadimplência e pagamentos. |

Os modelos Gold do MVP são `mart_carteira_credito`, `mart_inadimplencia`
e `fato_pagamentos`, construídos a partir dos modelos Silver.

## Testes dbt implementados (Fases 6 e 7)

| Alvo | Teste |
|---|---|
| Fontes Bronze | `not_null` e `unique` nas chaves de `customers`, `contracts` e `installments` |
| `silver_customers.customer_id` | `unique`, `not_null` |
| `silver_contracts.contract_id` | `unique`, `not_null` |
| `silver_contracts.customer_id` | `relationships` para `silver_customers` |
| `silver_installments` | `not_null`, `accepted_values`, teste singular de unicidade composta e validade de valores |
| `silver_installments.contract_id` | `relationships` para `silver_contracts` |
| `customer_segment`, `product_type`, `status` | `accepted_values` |
| Datas e valores | `assert_contract_dates_consistent`, `assert_paid_at_after_contract_start` e `assert_installment_amounts_valid` |
| Chaves dos marts | `assert_unique_mart_carteira_credito_key`, `assert_unique_mart_inadimplencia_key` e `assert_unique_fato_pagamentos_key` |
| Bronze | `dbt source freshness` usando `ingested_at`, com aviso em 72h e erro em 168h |
| Falha de teste | `store_failures` em `bronze_dbt_test__audit.<nome_do_teste>` |

## Regras iniciais de qualidade

- Campos obrigatórios não nulos, chaves únicas conforme granularidade e
  domínio de status/produto válido.
- Datas coerentes: `end_date > start_date`; pagamento não ocorre antes
  do contrato; valores são não negativos e parcelas não ultrapassam o
  valor devido.
- Parcelas sem contrato e contratos sem cliente são detectados por testes
  de relacionamento. Nenhum registro inválido é descartado em silêncio.
- Regra da inadimplência implementada: parcela com vencimento anterior à
  data de referência, sem pagamento integral até essa data e com status
  `open` ou `overdue`.
- Exclusões não são inferidas pela ausência de um registro em um arquivo.
- Os testes estão implementados no dbt. Falhas ficam em
  `bronze_dbt_test__audit` e o resumo em `ops.dq_results`. O campo
  `rejected_count` é a diferença não negativa entre contagens de Bronze e
  Silver; não existe ainda uma tabela física de registros rejeitados.

## Limites assumidos

- Uma parcela equivale a no máximo um pagamento integral; pagamentos
  parciais, estornos, renegociação e histórico de múltiplas alterações
  ficam fora do MVP.
- O indicador de carteira usa principal original de contratos ativos
  como aproximação, não saldo devedor amortizado. Uma evolução poderá
  incluir cronograma de amortização e apropriação de juros.

## Notas de implementação

- `updated_at` e `ingested_at` são `TIMESTAMP` em UTC.
- Chaves incrementais no dbt: `customer_id`; `contract_id`; e
  (`contract_id`, `installment_number`).
- Modelos Silver usam `merge`, partição por `updated_at` e clustering
  pelas chaves de negócio.
- A janela inicial para dados atrasados é de 3 dias, ajustável após
  validação; `ingested_at` desempata versões do mesmo `updated_at`.
- O `batch_id` é estável por conteúdo; o caminho no GCS não participa da
  identidade do lote.
- Reexecutar um lote já concluído deve ser evitado pelo estado em `ops`;
  se ocorrer, o `merge` do dbt mantém o resultado idempotente.
