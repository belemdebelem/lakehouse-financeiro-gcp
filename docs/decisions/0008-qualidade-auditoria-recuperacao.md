# ADR 0008 — Qualidade, auditoria de testes e recuperação da Fase 7

- **Status:** aceita e validada na Fase 7
- **Data:** 2026-11-19

## Contexto

A Fase 6 entregou modelos, testes e documentação dbt, mas ainda não
persistia falhas de testes, não verificava a atualidade da Bronze nem
registrava contagens de qualidade por lote. A Fase 7 precisa tornar essas
verificações rastreáveis e definir como uma execução interrompida pode ser
retomada sem duplicidade.

## Decisão

O Terraform cria o dataset `bronze_dbt_test__audit` e concede
`roles/bigquery.dataEditor` nele à conta de serviço `lakehouse-dbt`. No
dbt, `data_tests` configura explicitamente `+store_failures: true` e
`+schema: bronze_dbt_test__audit`. A macro `generate_schema_name` trata
testes cujo schema termina em `_dbt_test__audit` como exceção: o nome é
usado exatamente em qualquer target, sem acrescentar `_dev`. Assim, a
auditoria não depende do schema padrão do perfil nem cria datasets
paralelos.

A fonte `bronze` usa `loaded_at_field: ingested_at` com
`warn_after=72h` e `error_after=168h`, definidos dentro de `config:` em
`sources.yml` para evitar o aviso de deprecation do dbt 1.12. Os limiares
são adequados a um pipeline manual e compatíveis com o lote estático da
demonstração.

O resumo de qualidade é gravado em `ops.dq_results`, criado pelo DDL
versionado `sql/ops/dq_results.sql`. O módulo `src/lakehouse/quality.py`
lê os artefatos `run_results.json` e `sources.json`, conta linhas na
Bronze e na Silver do target ativo, calcula a diferença
`input_count - output_count` como `rejected_count` e grava o resumo com
`load_table_from_json` no decorador de partição
`ops.dq_results$YYYYMMDD` usando `WRITE_TRUNCATE`. A chave lógica é
(`ingestion_date`, `entity`, `metric_name`), com `PRIMARY KEY ...
NOT ENFORCED`.

`rejected_count` é uma aproximação explícita: o projeto ainda não tem uma
tabela dedicada a registros rejeitados, prevista para evolução futura.

## Alternativas consideradas

- **Confiar no schema padrão do dbt e criar o dataset de forma implícita:**
  menos configuração, mas deixaria a criação do dataset dependente de
  permissões amplas e poderia gerar nomes sufixados por target.
- **Gravar falhas no próprio dataset `bronze`:** evitaria dataset novo, mas
  misturaria artefatos de auditoria com dados de negócio.
- **Limiares de 48h/72h:** mais rigorosos, porém gerariam aviso ou falha
  com o lote estático usado na demonstração.
- **`DELETE` + `INSERT` em `ops.dq_results`:** forma mais óbvia de
  substituir linhas, mas `insert_rows_json` deixou buffer de streaming e o
  `DELETE` falhou. Carga por arquivo com `WRITE_TRUNCATE` na partição é
  atômica, não gera buffer e foi validada em duas execuções.
- **Gerar `ops.dq_results` como modelo dbt:** simplificaria a consulta,
  mas misturaria metadados operacionais com a camada analítica e exigiria
  tratar o próprio resumo como dependência do build.

## Consequências

- Falhas de testes podem ser inspecionadas em tabelas
  `bronze_dbt_test__audit.*` até a próxima execução do mesmo teste, que
  substitui os resultados anteriores. Em execuções sem falhas, as tabelas
  ficam vazias.
- `dbt source freshness` produz `sources.json` com `results[]`, `status` e
  `max_loaded_at_time_ago_in_s`; o parser do resumo usa esse formato real.
- Reexecutar o resumo de qualidade para a mesma data substitui a partição,
  sem acumular duplicatas. A tabela de teste afetada pelo buffer de
  streaming foi recriada a partir do DDL versionado antes da validação
  final.
- A simulação de falha entre etapas usa um `as_of_date` inválido: a Silver
  termina e a Gold falha. A retomada é feita com o `as_of_date` correto e
  um `dbt build` normal; não é necessário limpar tabelas.
- Nenhuma dependência Python nova é adicionada; `google-cloud-bigquery`
  e a stdlib são suficientes.
