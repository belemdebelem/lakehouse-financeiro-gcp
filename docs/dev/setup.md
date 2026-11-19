# Setup e execução local (Fases 1 a 6 — concluídas)

## Pré-requisitos

- Python >= 3.11
- `uv` para instalar a partir do lockfile (`python -m pip install uv`)

## Instalação

```bash
uv sync --extra dev
```

O `uv.lock` fixa `pytest`, `ruff` e as dependências transitivas. Não
editar o lockfile manualmente: após mudar `pyproject.toml`, rode
`uv lock` e versione o resultado no mesmo commit.

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
- `DBT_TARGET` seleciona o perfil do dbt; o padrão é `dev`. `prod` grava
  em `silver`/`gold`; `dev` grava em `silver_dev`/`gold_dev`.
- Definir `GOOGLE_CLOUD_PROJECT` com o mesmo `GCP_PROJECT_ID` evita avisos
  do cliente BigQuery durante comandos dbt.

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

## Testes e lint

```bash
uv run pytest -q
uv run ruff check .
uv lock --check
```

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

`apply` e `destroy` só com aprovação explícita. O orçamento e os alertas
de faturamento são configurados manualmente; veja
`infrastructure/terraform/README.md`.

## Observações

- Fase 1 concluída: instalação travada por `uv.lock`, testes de
  configuração, lint configurado e nenhuma credencial versionada.
- Fase 2 concluída: gerador determinístico, amostras válidas e inválidas,
  esquema em código e testes de reprodutibilidade.
- Fase 3 concluída: Terraform mínimo, state local e orçamento revisado.
- Fase 4 concluída: ingestão validada, checksum, caminho particionado,
  não sobrescrita e testes com client fake.
- Fase 5 concluída: DDL versionado, carga GCS → staging → Bronze com
  `MERGE`, estado em `ops` e reexecução idempotente.
- Fase 6 concluída: dbt pinado, perfis `dev`/`prod`, schemas isolados,
  modelos Silver incrementais, três marts Gold, testes e docs gerados.
- `docs/dev/fase1-evolucao.md` registra como estes artefatos serão
  atualizados em cada fase seguinte.
