# Setup e execução local (Fases 1 a 4 — concluídas)

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
  `LOG_LEVEL=INFO`, `GCP_PROJECT_ID` e `GCS_BUCKET_NAME` vazios.
- Autenticação GCP local: `gcloud auth application-default login`. Não
  usar chaves JSON de service account no repositório.
- `GCS_BUCKET_NAME` é lido pela ingestão da Fase 4; `BQ_DATASET_*` entram
  na Fase 5.

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
- `docs/dev/fase1-evolucao.md` registra como estes artefatos serão
  atualizados em cada fase seguinte.
