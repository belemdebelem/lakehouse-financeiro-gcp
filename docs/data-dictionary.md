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
- Regras analíticas e testes do dbt permanecem previstos para as Fases 6
  e 7; a validação Python desta fase é apenas estrutural.

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

## Mapeamento para dbt

| Bronze (source) | Modelo Silver | Uso principal |
|---|---|---|
| `bronze.customers` | `silver_customers` | Base de cliente e segmento. |
| `bronze.contracts` | `silver_contracts` | Carteira, produto, status e datas. |
| `bronze.installments` | `silver_installments` | Inadimplência e pagamentos. |

Os modelos Gold do MVP são `mart_carteira_credito`, `mart_inadimplencia`
e `fato_pagamentos`, construídos a partir dos modelos Silver.

## Testes dbt previstos

| Alvo | Teste |
|---|---|
| `silver_customers.customer_id` | `unique`, `not_null` |
| `silver_contracts.contract_id` | `unique`, `not_null` |
| `silver_contracts.customer_id` | `relationships` para `silver_customers` |
| `silver_installments` | `not_null` nas chaves e teste singular de unicidade composta |
| `silver_installments.contract_id` | `relationships` para `silver_contracts` |
| `customer_segment`, `product_type`, `status` | `accepted_values` |
| Datas e valores | testes singulares |
| Bronze | `dbt source freshness` usando `ingested_at` |

## Regras iniciais de qualidade

- Campos obrigatórios não nulos, chaves únicas conforme granularidade e
  domínio de status/produto válido.
- Datas coerentes: `end_date > start_date`; pagamento não ocorre antes
  do contrato; valores são não negativos e parcelas não ultrapassam o
  valor devido.
- Parcelas sem contrato e contratos sem cliente são contabilizados como
  inválidos/rejeitados; nenhum registro inválido é descartado em
  silêncio.
- Regra da inadimplência: parcela vencida na data de referência, sem
  pagamento integral até essa data. A regra exata será implementada e
  testada na fase de transformações.
- Exclusões não são inferidas pela ausência de um registro em um arquivo.
- Os testes serão implementados no dbt; falhas serão persistidas com
  `store_failures` e resumidas em `ops.dq_results`.

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
