# Runbook de qualidade, recuperação e observabilidade

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

## CI/CD e segurança (Fase 8)

Verificações locais antes do push:

```bash
uv run pytest -q
uv run ruff check .
uv run sqlfluff lint dbt/models
uv run pre-commit run --all-files
```

O workflow `CI` bloqueia PRs com falha de testes, lint, SQLFluff,
`dbt parse`, Terraform, Gitleaks ou Checkov. `dbt compile` usa WIF e só
executa em PRs do próprio repositório; forks recebem as verificações sem
credenciais GCP.

Para promover mudanças:

1. Rodar `CD - Terraform` com `action=plan` e conferir o plano publicado.
2. Rodar novamente com `action=apply`; o job depende do environment `demo`
   com revisores configurados no GitHub.
3. Rodar `DBT - Build controlado` com `ingestion_date`; também exige
   `demo`. O workflow publica `manifest.json`, `catalog.json`,
   `run_results.json`, `sources.json`, SQL compilado e `dbt.log`.

Se o `apply` falhar por WIF, confira `GCP_WIF_PROVIDER`, as variáveis de SA
e se o principal do repositório já foi criado no GCP. Se o build dbt falhar
por freshness, execute a ingestão/carga do lote e repita o dispatch; se
falhar por teste de modelo, inspecione
`bronze_dbt_test__audit.<nome_do_teste>` como na Fase 7.

WIF, conta `lakehouse-ci` e backend GCS foram aplicados. O state do
Terraform está no bucket do lakehouse, no prefixo
`terraform/state/lakehouse-financeiro`; o `plan` posterior do CD terminou
sem mudanças. As variáveis do GitHub e o revisor obrigatório do environment
`demo` também foram configurados. Consulte o ADR 0009 para o registro da
implantação.

## Observabilidade (Fase 9)

Os comandos Python emitem JSON localmente e enviam eventos à API Cloud
Logging apenas quando `CLOUD_LOGGING_ENABLED=true`. O workflow de build já
habilita essa variável. Eventos trazem `pipeline_name`, etapa, status, data,
duração e identificadores dos lotes; o resumo de qualidade acrescenta
`invocation_id` e contagens dbt/lineage.

Para localizar eventos no Logs Explorer:

```text
logName="projects/<PROJECT_ID>/logs/lakehouse-financeiro-pipeline"
jsonPayload.pipeline_name="lakehouse-financeiro"
```

Para falhas:

```text
logName="projects/<PROJECT_ID>/logs/lakehouse-financeiro-pipeline"
jsonPayload.status="failure"
```

A política Terraform de Cloud Monitoring está aplicada para esse filtro e
associada a um canal de e-mail configurado por `TF_VAR_alert_email`. Em
2026-11-20, a API do Monitoring confirmou um incidente `OPEN` após eventos
sintéticos. O canal aparece habilitado, mas a API não informa status de
verificação e não foi possível confirmar a entrega na caixa postal. Não use
uma falha de dados reais para o teste.

O envio explícito aumenta o volume ingerido no Cloud Logging. A página de
[preços](https://cloud.google.com/logging#pricing) informa franquia de 50
GiB por projeto/mês e tarifa de armazenamento acima dela. Uma política
log-based custa cerca de US$ 0,035/mês segundo os
[exemplos de preços](https://cloud.google.com/stackdriver/observability-pricing-examples).
O volume desta demonstração é pequeno, mas a franquia é compartilhada por
todo o projeto.

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
