# Setup e execução local (Fases 1 e 2 — concluídas)

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
  `LOG_LEVEL=INFO` e `GCP_PROJECT_ID` vazio.
- Autenticação GCP local: `gcloud auth application-default login`. Não
  usar chaves JSON de service account no repositório.
- `GCS_BUCKET_NAME` e `BQ_DATASET_*` constam no template, mas ainda não
  são lidos pelo código; entram nas Fases 4 e 5.

## Dados sintéticos (Fase 2)

Os CSVs versionados em `data/sample/` são regeneráveis com:

```bash
uv run python -m lakehouse.generation
```

O comando usa a seed `20261117`, sobrescreve apenas os três arquivos da
pasta e não acessa a nuvem. `data/sample/invalid/` contém exemplos
rejeitados por `validate_dataset`, usados nos testes do esquema.

## Testes e lint

```bash
uv run pytest -q
uv run ruff check .
uv lock --check
```

## Observações

- Fase 1 concluída: instalação travada por `uv.lock`, testes de
  configuração, lint configurado e nenhuma credencial versionada.
- Fase 2 concluída: gerador determinístico, amostras válidas e inválidas,
  esquema em código e testes de reprodutibilidade.
- `docs/dev/fase1-evolucao.md` registra como estes artefatos serão
  atualizados em cada fase seguinte.
