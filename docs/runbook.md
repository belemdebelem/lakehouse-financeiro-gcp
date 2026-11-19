# Runbook de qualidade e recuperação

Este procedimento cobre a Fase 7. Use ADC local e variáveis de `.env`
carregadas no shell. Substitua `<PROJECT_ID>` pelo projeto configurado.

## Sequência normal

```bash
set -a; source .env; set +a
export GOOGLE_CLOUD_PROJECT="$GCP_PROJECT_ID"

uv run dbt build --project-dir dbt --profiles-dir dbt --target dev
uv run dbt test --project-dir dbt --profiles-dir dbt --target dev
uv run dbt source freshness --project-dir dbt --profiles-dir dbt --target dev
uv run python -m lakehouse.quality --ingestion-date 2026-11-17
```

`dbt build` já executa os testes; o `dbt test` explícito garante que
`run_results.json` reflita a última verificação e que as tabelas de falha
sejam atualizadas.

## Inspeção de falhas

As falhas ficam em
`<PROJECT_ID>.bronze_dbt_test__audit.<nome_do_teste>`. Cada execução de um
teste substitui a tabela anterior daquele teste.

```bash
uv run python - <<'PY'
from google.cloud import bigquery

client = bigquery.Client(project="<PROJECT_ID>", location="southamerica-east1")
rows = client.query(
    "SELECT table_name FROM `<PROJECT_ID>.bronze_dbt_test__audit.INFORMATION_SCHEMA.TABLES` "
    "ORDER BY table_name"
).result()
for row in rows:
    print(row.table_name)
PY
```

## Freshness

`dbt source freshness` grava `dbt/target/sources.json`. Os limiares são
72 horas para aviso e 168 horas para erro, medidos por
`bronze.*.ingested_at`. Se o lote estiver parado por mais de 7 dias, o
comando retorna erro; isso indica necessidade de nova ingestão/carga, não
falha do dbt.

## Resumo de qualidade

`ops.dq_results` registra por data, entidade e métrica:

- `input_count`: linhas na Bronze.
- `output_count`: linhas na Silver do target ativo.
- `rejected_count`: diferença não negativa entre entrada e saída.
- `dbt_tests_passed` e `dbt_tests_failed`: contagens de `run_results.json`.
- `source_freshness_max_age_hours`: maior idade entre as tabelas da Bronze,
  lida de `sources.json`.

O DDL está em `sql/ops/dq_results.sql`. A gravação usa
`load_table_from_json` com `WRITE_TRUNCATE` na partição
`ops.dq_results$YYYYMMDD`; não há `DELETE`, buffer de streaming nem Mutation
API. Reexecutar o comando para a mesma data substitui as 12 linhas do
resumo sem duplicidade.

```bash
uv run python -m lakehouse.quality --ingestion-date 2026-11-17
```

Se a tabela tiver sido criada por uma versão antiga com
`insert_rows_json`, recrie-a a partir do DDL versionado antes de usar a
escrita particionada. A validação final deste projeto fez isso e confirmou
12 linhas `PASS` em duas execuções consecutivas.

O teste de integração opt-in verifica a idempotência diretamente no
BigQuery:

```bash
RUN_DQ_INTEGRATION=1 uv run pytest tests/integration/test_quality_dq.py -q
```

## Falha entre etapas e retomada

Para simular uma falha após a Silver e antes da Gold:

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --target dev \
  --vars '{"as_of_date": "2026-13-99"}' --select silver+ gold+ \
  || echo "FALHA_SIMULADA exit=$?"
```

A data inválida faz os marts Gold falharem; os modelos Silver já gravados
permanecem. Na validação real, a Silver terminou com `MERGE (0.0 rows)` e
a Gold falhou. Para retomar:

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --target dev
uv run dbt test --project-dir dbt --profiles-dir dbt --target dev
uv run dbt source freshness --project-dir dbt --profiles-dir dbt --target dev
uv run python -m lakehouse.quality --ingestion-date 2026-11-17
```

Após a retomada, o build voltou a `PASS=83 WARN=0 ERROR=0`, o teste a
`PASS=77` e o resumo a 12 linhas `PASS`. Não é necessário limpar tabelas: a
Silver usa `merge` e a Gold recria as tabelas. Se um teste falhar, corrija
a causa na origem, no DDL ou no modelo antes de rerodar; não desative o
teste. Para isolar uma falha persistente, inspecione
`bronze_dbt_test__audit.<nome_do_teste>` e os artefatos em `dbt/target/`.

## Limitações

- `rejected_count` é uma diferença observada entre Bronze e Silver, não uma
  tabela de registros rejeitados.
- `store_failures` mantém apenas o estado mais recente de cada teste.
- O resumo usa `DBT_TARGET`; `dev` lê `silver_dev`/`gold_dev` e `prod` lê
  `silver`/`gold`.
- Freshness depende de `ingested_at`, preenchido na carga da Fase 5.
- O comando de qualidade pressupõe que `dbt test` e `dbt source freshness`
  tenham sido executados antes, para que os artefatos em `dbt/target/`
  reflitam a execução atual.
