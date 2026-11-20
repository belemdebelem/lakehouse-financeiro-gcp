# Setup e execução local (Fases 1 a 10 concluídas)

## Pré-requisitos

- Python >= 3.11
- `uv` para instalar a partir do lockfile (`python -m pip install uv`)

## Instalação

```bash
uv sync --extra dev
```

O `uv.lock` fixa `pytest`, `ruff`, `sqlfluff`, `pre-commit` e as
dependências transitivas. Não editar o lockfile manualmente: após mudar
`pyproject.toml`, rode `uv lock` e versione o resultado no mesmo commit.

Sem `uv`, é possível usar `python3 -m venv .venv`, ativar o ambiente e
rodar `python -m pip install -e '.[dev]'`, mas isso não garante as
mesmas versões do lockfile.

## Configuração

- Copie `.env.example` para `.env` (não versionar) e preencha fora do
  repositório, sem valores reais no template versionado.
- `Settings` lê variáveis de ambiente diretamente; para carregar o
  `.env` no shell: `set -a; source .env; set +a`.
- Defaults em `src/lakehouse/config.py`: região e localização
  `southamerica-east1`, `PIPELINE_NAME=lakehouse-financeiro`,
  `LOG_LEVEL=INFO`, `GCP_PROJECT_ID` e `GCS_BUCKET_NAME` vazios, datasets
  `bronze`, `silver`, `gold` e `ops`.
- Autenticação GCP local: `gcloud auth application-default login`. Não
  usar chaves JSON de service account no repositório.
- `GCS_BUCKET_NAME` é lido pela ingestão da Fase 4; `BQ_DATASET_*` são
  lidos pela carga da Fase 5 e pelo dbt na Fase 6.
- `DBT_TARGET` seleciona o perfil do dbt e o dataset Silver lido pelo
  resumo de qualidade; o padrão é `dev`. `prod` grava em `silver`/`gold`;
  `dev` grava em `silver_dev`/`gold_dev`. O schema de auditoria
  `bronze_dbt_test__audit` não recebe sufixo `_dev`.
- Definir `GOOGLE_CLOUD_PROJECT` com o mesmo `GCP_PROJECT_ID` evita avisos
  do cliente BigQuery durante comandos dbt.
- `CLOUD_LOGGING_ENABLED` controla o envio explícito dos logs Python ao
  Cloud Logging; o padrão é `false`. Habilite-o somente com ADC/WIF e a
  permissão `roles/logging.logWriter` aplicada à identidade.

## Dados sintéticos (Fase 2)

Os CSVs versionados em `data/sample/` são regeneráveis com:

```bash
uv run python -m lakehouse.generation
```

O comando usa a seed `20261117`, sobrescreve apenas os três arquivos da
pasta e não acessa a nuvem. `data/sample/invalid/` contém exemplos
rejeitados por `validate_dataset`, usados nos testes do esquema.

## Ingestão para GCS (Fase 4)

A dependência oficial `google-cloud-storage` está travada em `uv.lock`.
Com ADC ativo e `GCS_BUCKET_NAME` definido no ambiente:

```bash
set -a; source .env; set +a
uv run python -m lakehouse.ingestion
```

O comando valida os CSVs versionados, calcula SHA-256, grava metadados no
objeto e envia cada arquivo para
`landing/<entidade>/ingestion_date=YYYY-MM-DD/<arquivo>`. A precondição
`if_generation_match=0` impede sobrescrita silenciosa; arquivos inválidos
são rejeitados antes de qualquer upload.

O teste de integração controlado é opt-in e idempotente:

```bash
RUN_GCS_INTEGRATION=1 uv run pytest tests/integration -q
```

## Carga BigQuery Bronze (Fase 5)

Os schemas das tabelas Bronze e `ops` são definidos somente pelo SQL
versionado em `sql/bronze/` e `sql/ops/`. Os datasets e o IAM continuam
sendo criados pelo Terraform. Com ADC ativo, aplique o DDL:

```bash
uv run python - <<'PY'
from pathlib import Path
from google.cloud import bigquery

client = bigquery.Client(location="southamerica-east1")
for name in (
    "sql/bronze/tables.sql",
    "sql/bronze/staging_tables.sql",
    "sql/ops/ingestion_batches.sql",
    "sql/ops/dq_results.sql",
):
    for statement in Path(name).read_text().split(";"):
        if statement.strip():
            client.query(statement).result()
PY
```

Depois carregue os objetos de uma data específica:

```bash
set -a; source .env; set +a
INGESTION_DATE=2026-11-17 uv run python -m lakehouse.loading
```

A carga grava em `<entidade>_staging` com schema explícito e substitui o
conteúdo da staging; em seguida aplica `MERGE` na tabela final pela chave
de negócio. O lote é registrado em `ops.ingestion_batches` com `STARTED`,
`SUCCEEDED` ou `FAILED`. Reexecutar um lote já `SUCCEEDED` não recarrega
nem duplica registros.

O teste de integração controlado contra o BigQuery usa a data
`2026-11-17` e é opt-in:

```bash
RUN_BQ_INTEGRATION=1 uv run pytest tests/integration/test_bigquery_load.py -q
```

## Transformações dbt (Fase 6)

As dependências `dbt-core==1.12.6` e `dbt-bigquery==1.12.3` vêm do
`pyproject.toml`/`uv.lock`. `profiles.yml` usa ADC e `env_var`, sem
segredos. Com o `.env` carregado e ADC ativo:

```bash
set -a; source .env; set +a
export GOOGLE_CLOUD_PROJECT="$GCP_PROJECT_ID"

uv run dbt parse --project-dir dbt --profiles-dir dbt --target dev
uv run dbt compile --project-dir dbt --profiles-dir dbt --target dev
uv run dbt build --project-dir dbt --profiles-dir dbt --target dev
uv run dbt docs generate --project-dir dbt --profiles-dir dbt --target dev
```

Use `DBT_TARGET=prod` apenas quando a gravação em `silver`/`gold` for
intencional. Artefatos em `dbt/target/`, `dbt/logs/` e `dbt/dbt_packages/`
são ignorados pelo Git. Para reconstruir todas as tabelas em `dev`:

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --target dev --full-refresh
```

## Qualidade, auditoria e recuperação (Fase 7)

Com ADC ativo, `.env` carregado e os artefatos do dbt atualizados:

```bash
set -a; source .env; set +a
export GOOGLE_CLOUD_PROJECT="$GCP_PROJECT_ID"

uv run dbt test --project-dir dbt --profiles-dir dbt --target dev
uv run dbt source freshness --project-dir dbt --profiles-dir dbt --target dev
uv run python -m lakehouse.quality --ingestion-date 2026-11-17
```

`dbt test` grava falhas em `bronze_dbt_test__audit` quando houver; em uma
execução sem falhas, as tabelas de auditoria ficam vazias. `dbt source
freshness` grava `dbt/target/sources.json` com aviso em 72 horas e erro em
168 horas, medidos por `bronze.*.ingested_at`. O módulo de qualidade lê
`run_results.json` e `sources.json`, conta linhas na Bronze e na Silver do
target ativo e grava 12 linhas em `ops.dq_results`.

A escrita usa `load_table_from_json` com `WRITE_TRUNCATE` na partição
`ops.dq_results$YYYYMMDD`; não usa streaming nem `DELETE`. Reexecutar o
comando para a mesma data substitui o resumo anterior. O procedimento
completo de diagnóstico, simulação de falha e retomada está em
`docs/runbook.md`.

O teste de integração do resumo é opt-in e exige os artefatos do dbt:

```bash
RUN_DQ_INTEGRATION=1 uv run pytest tests/integration/test_quality_dq.py -q
```

## Testes e lint

```bash
uv run pytest -q
uv run ruff check .
uv run sqlfluff lint dbt/models
uv lock --check
```

## CI/CD e DevSecOps (Fase 8)

Instale os hooks uma vez por clone e execute todos antes do push:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

O hook de SQL usa `.sqlfluff`, o de Python usa `ruff` e o Gitleaks usa
`.gitleaks.toml`. O Checkov roda no CI com `.checkov.yml`.

Os workflows ficam em `.github/workflows/`:

- `ci.yml`: `pull_request`/`push` em `main`; testes, lint, SQLFluff,
  `dbt parse`, `dbt compile`, Terraform, Gitleaks e Checkov. `dbt compile`
  usa WIF e é ignorado em PRs de forks.
- `cd.yml`: `workflow_dispatch` com `plan` e `apply` separados. O `apply`
  só roda em `main` e exige o environment `demo` com revisores.
- `dbt-build.yml`: `workflow_dispatch` com `ingestion_date`, environment
  `demo`, ingestão/carga com a SA do pipeline, dbt/qualidade com a SA do
  dbt e upload de `index.html`, `catalog.json`, manifest, resultados e SQL
  compilado como artefato `dbt-artifacts` por 14 dias.

Configure como variáveis do repositório: `GCP_PROJECT_ID`, `GCP_REGION`,
`GCS_BUCKET_NAME`, `BQ_DATASET_BRONZE`, `BQ_DATASET_SILVER`,
`BQ_DATASET_GOLD`, `BQ_DATASET_OPS`, `GCP_WIF_PROVIDER`, `GCP_CI_SA`,
`GCP_PIPELINE_SA` e `GCP_DBT_SA`. Nenhuma chave JSON é necessária.
O `GITHUB_TOKEN` é suficiente para o Gitleaks.

## Observabilidade (Fase 9)

Os CLIs Python escrevem JSON no stdout. Para enviar eventos ao Cloud Logging
em execução local, configure ADC e confirme que o usuário/conta dispõe de
`roles/logging.logWriter`:

```bash
set -a; source .env; set +a
export CLOUD_LOGGING_ENABLED=true
uv run python -m lakehouse.loading
```

O workflow `DBT - Build controlado` habilita a variável para as contas WIF
do pipeline e do dbt. Em Logs Explorer, filtre por
`jsonPayload.pipeline_name="lakehouse-financeiro"`; use `batch_id`,
`stage`, `status` e `duration_seconds` para rastrear as etapas. O resumo de
qualidade também registra `invocation_id`, tempo de execução, resultados
dos testes/modelos, linhas afetadas e quantidades do manifest.

Terraform aplica uma política que abre incidente no Cloud Monitoring para
eventos `jsonPayload.status="failure"` e associa o canal de e-mail fornecido
por `TF_VAR_alert_email` (não versione esse valor). Em 2026-11-20, a API do
Monitoring confirmou um incidente `OPEN` após eventos sintéticos e o canal
apareceu habilitado. Em 2026-11-20, a pessoa responsável confirmou o
recebimento do e-mail de alerta.

Cloud Logging inclui 50 GiB por projeto/mês; armazenamento acima desse
volume é tarifado. O volume deste MVP é baixo, mas a franquia é compartilhada
por todo o projeto. Verifique [preços atuais do Cloud Logging](https://cloud.google.com/logging#pricing)
e a estimativa da política de alertas no Console antes de aplicar.

Validação de 2026-11-19: CI verde em `Checks`, `dbt compile`, `Terraform` e
`Gitleaks`; CD `plan` sem mudanças; build dbt com aprovação do environment
`demo` e `PASS=83`, artefato `dbt-artifacts` publicado e 12 linhas `PASS` em
`ops.dq_results` para `2026-11-17`. O `apply` inicial criou 15 recursos e o
state foi migrado para `terraform/state/lakehouse-financeiro`.

## Infraestrutura (Fase 3)

A configuração Terraform fica em `infrastructure/terraform/`. Requer
`gcloud auth application-default login` (ADC) e um projeto com
faturamento ativo. Não use chaves JSON.

```bash
cd infrastructure/terraform
terraform init
terraform fmt -check -recursive
terraform validate
cp terraform.tfvars.example terraform.tfvars
terraform plan
```

O backend GCS já está ativo no prefixo
`terraform/state/lakehouse-financeiro`. O CD gera `backend.tf` e
`backend.hcl` a partir das variáveis do repositório; para executar Terraform
localmente, configure o backend GCS e inicialize o workspace existente antes
de planejar mudanças. `apply` e `destroy` só com aprovação explícita. O
orçamento e os alertas de faturamento são configurados manualmente; veja
`infrastructure/terraform/README.md`.

## Encerramento e limpeza

Para revisar mudanças de infraestrutura, use o workflow `CD - Terraform`
com `action=plan`. O `apply` exige aprovação no environment `demo`. Para
encerrar a demonstração, remova recursos somente após revisar o plano de
destruição e obter autorização explícita; a configuração permite apagar
objetos e dados dos datasets. Consulte os passos e impactos em
[`infrastructure/terraform/README.md`](../../infrastructure/terraform/README.md#limpeza-e-custo).

Os artefatos dbt ficam anexados à execução do workflow `DBT - Build
controlado` por 14 dias. Na página da execução, baixe `dbt-artifacts` e abra
`index.html` localmente para consultar catálogo e lineage.

## Observações

- Fase 1 concluída: instalação travada por `uv.lock`, testes de
  configuração, lint configurado e nenhuma credencial versionada.
- Fase 2 concluída: gerador determinístico, amostras válidas e inválidas,
  esquema em código e testes de reprodutibilidade.
- Fase 3 concluída: Terraform mínimo provisionado e orçamento revisado; o
  state foi migrado para GCS na Fase 8.
- Fase 4 concluída: ingestão validada, checksum, caminho particionado,
  não sobrescrita e testes com client fake.
- Fase 5 concluída: DDL versionado, carga GCS → staging → Bronze com
  `MERGE`, estado em `ops` e reexecução idempotente.
- Fase 6 concluída: dbt pinado, perfis `dev`/`prod`, schemas isolados,
  modelos Silver incrementais, três marts Gold, testes e docs gerados.
- Fase 7 concluída: `DBT_TARGET` usado no resumo, `store_failures` em
  `bronze_dbt_test__audit`, freshness na Bronze, DDL e CLI em
  `ops.dq_results`, testes unitários e integração opt-in de idempotência.
- Fase 8 concluída: SQLFluff, pre-commit, Gitleaks, Checkov, workflows com
  WIF e backend GCS aplicados; state migrado, variáveis do GitHub e revisores
  do environment `demo` configurados. O CI/CD foi validado.
- Fase 9 concluída: logs estruturados, alerta por log e canal de e-mail
  aplicados; incidente e recebimento da notificação sintética confirmados.
- Fase 10 concluída: README público, especificação, diagrama, métricas
  observadas, roteiro de palestra e artefatos dbt de curta retenção
  documentados.
