# ADR 0002 — dbt-core para Silver e Gold

- **Status:** aceita
- **Data:** 2026-11-08

## Contexto

O pipeline precisa transformar a Bronze em Silver e Gold com regras
versionadas, testes, incrementalidade e rastreabilidade. A alternativa
manual exigiria construir e manter DAG, lineage, testes e documentação.
O projeto é um portfólio e deve demonstrar práticas reconhecidas de
DataOps sem adicionar serviços gerenciados caros.

## Alternativas consideradas

1. Runner Python próprio executando SQL versionado.
2. dbt-core + dbt-bigquery, executado localmente e no CI.
3. dbt Cloud.
4. Processamento distribuído com Dataflow/Beam.

## Decisão

Adotar dbt-core + dbt-bigquery para Silver e Gold, mantendo Python na
ingestão, validação e carga da Bronze.

- `sources.yml` declara `bronze.customers`, `bronze.contracts` e
  `bronze.installments`.
- Modelos Silver usam `merge`, `unique_key`, partição, cluster e janela
  de segurança para dados atrasados.
- Modelos Gold respondem às perguntas analíticas do MVP e podem usar
  contratos de modelo.
- Testes genéricos e singulares, `store_failures` e `source freshness`
  fazem parte do fluxo.
- `dbt docs` e o `manifest.json` fornecem lineage e documentação.
- `profiles.yml` não contém segredos; usa ADC local e WIF/ADC no GitHub
  Actions.
- dbt Cloud, Semantic Layer e Mesh ficam fora do MVP.
- dbt packages externos só entram com necessidade justificada.

## Consequências

- O projeto ganha DAG, lineage, testes e documentação com pouco código
  próprio.
- Há uma dependência adicional e a necessidade de pinar `dbt-core` e
  `dbt-bigquery` no lockfile.
- Jinja e macros podem esconder lógica; os modelos devem permanecer
  simples e revisados.
- dbt não é orquestrador; o pipeline Python e o GitHub Actions
  controlam a ordem ingestão → Bronze → `dbt build`.
- Em pull requests, o CI usa `dbt parse`, `dbt compile` e `sqlfluff`;
  `dbt build` completo fica para execução manual ou branch principal
  para controlar custo e tempo.
- `store_failures` cria tabelas de auditoria; a retenção deve ser curta.

## Critérios de reversão

Reavaliar se o número de modelos crescer a ponto de exigir seleção e
deferimento complexos, se o custo de CI ficar desproporcional ou se
surgir necessidade de orquestração e agendamento que o GitHub Actions
não atenda.

## Fontes

- [dbt documentation](https://docs.getdbt.com/docs/introduction)
- [dbt BigQuery setup](https://docs.getdbt.com/docs/core/connect-data-platform/bigquery-setup)
