# Contrato de evolução da Fase 1

A Fase 1 entrega a base reproduzível mínima. Ela não é congelada: cada
fase seguinte atualiza os mesmos arquivos, no mesmo commit da feature,
sem criar configuração paralela. Este documento é a referência das
tarefas "Atualizar os artefatos da Fase 1" listadas no README.

## Regras

1. `pyproject.toml` é a única fonte de dependências. Ao adicionar ou
   remover pacote, rode `uv lock` e versione `uv.lock` no mesmo commit.
2. `.env.example`, testes e documentação contêm apenas nomes de
   variáveis e valores fictícios; nunca credenciais, chaves JSON ou IDs
   reais de projeto.
3. `Settings` (`src/lakehouse/config.py`) ganha campo apenas quando a
   fase passa a ler aquela variável. Defaults ficam no código, não em
   dois lugares.
4. Novas ferramentas só entram com necessidade demonstrável; a decisão
   é registrada em `docs/decisions/`.
5. `docs/dev/setup.md` acompanha comandos, variáveis e pré-requisitos
   novos na mesma alteração.
6. Testes, mocks e fixtures entram junto com a funcionalidade. Ao final
   de cada fase: `uv lock --check`, `uv run pytest -q` e
   `uv run ruff check .` devem passar.

## Matriz por fase

| Fase | Artefatos da Fase 1 atualizados | Mudança esperada |
|---|---|---|
| 2 | `pyproject.toml`/`uv.lock`, `tests/`, `docs/dev/setup.md` | Gerador com seed fixa e amostras; testes de reprodutibilidade e esquema. Preferir stdlib; nova dependência só se justificada. |
| 3 | `.gitignore`, `docs/dev/setup.md` | Comandos Terraform; passar a versionar `.terraform.lock.hcl` para fixar providers. Nenhuma dependência Python nova. |
| 4 | `pyproject.toml`/`uv.lock`, `config.py`, `.env.example`, `tests/`, `docs/dev/setup.md` | `google-cloud-storage`; `GCS_BUCKET_NAME` passa a ser lida; mocks de upload e precondição de geração. |
| 5 | `pyproject.toml`/`uv.lock`, `config.py`, `.env.example`, `tests/`, `docs/dev/setup.md` | `google-cloud-bigquery`; `BQ_DATASET_*` passam a ser lidas; mocks de carga e metadados de lote. |
| 6 | `pyproject.toml`/`uv.lock`, `.env.example`, `.gitignore`, `docs/dev/setup.md` | `dbt-core` e `dbt-bigquery` pinados juntos; variáveis do dbt; ignorar `target/`, `dbt_packages/` e `logs/`. |
| 7 | `config.py`, `tests/`, `docs/dev/setup.md` | `DBT_TARGET` passa a ser lido por `Settings`; testes unitários de parse/agregação/escrita e integração opt-in de idempotência; comandos de freshness e qualidade documentados. Nenhuma dependência nova. |
| 8 | `pyproject.toml`/`uv.lock`, `.gitignore`, `docs/dev/setup.md` | `sqlfluff` no extra `dev`; configuração de Gitleaks/Checkov e pre-commit; artefatos de CI. |
| 9 | `pyproject.toml`/`uv.lock`, `config.py`, `.env.example`, `tests/`, `docs/dev/setup.md` | Cliente de Cloud Logging se necessário; `LOG_LEVEL` já existe; logs estruturados e testes com mocks. |
| 10 | `README.md`, `docs/dev/setup.md` | README público, `docs/spec.md` e instruções finais de execução/limpeza. |

## Verificação

Ao final de cada fase, revisar o diff dos arquivos acima e executar:

```bash
uv lock --check
uv run pytest -q
uv run ruff check .
```

Status: Fase 1 concluída em 2026-11-17. Fase 4 executada em 2026-11-17:
`google-cloud-storage` adicionado, `GCS_BUCKET_NAME` passou a ser lida e
os testes com mocks de upload/precondição foram incluídos. Fase 5
executada em 2026-11-17: `google-cloud-bigquery` adicionado, `BQ_DATASET_*`
passaram a ser lidas, DDL versionado criado e testes com mocks de carga,
metadados de lote e idempotência incluídos. Fase 6 executada em
2026-11-19: `dbt-core` e `dbt-bigquery` pinados, `DBT_TARGET` documentado,
artefatos dbt adicionados ao `.gitignore` e `docs/dev/setup.md`
atualizado com parse/compile/build/docs. Fase 7 executada em 2026-11-19:
`Settings.dbt_target` passou a ser usada pelo resumo de qualidade,
`tests/unit/test_quality.py` cobre parsing, contagens, agregação e escrita
particionada, `tests/integration/test_quality_dq.py` valida idempotência no
BigQuery e `docs/dev/setup.md` documenta freshness, auditoria e qualidade.
As demais atualizações listadas são executadas dentro da fase
correspondente.
