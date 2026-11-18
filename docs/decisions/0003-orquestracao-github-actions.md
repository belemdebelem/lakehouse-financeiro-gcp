# ADR 0003 — GitHub Actions como orquestrador do MVP

- **Status:** aceita
- **Data:** 2026-11-08

## Contexto

O MVP tem poucas etapas batch: ingestão, carga Bronze e `dbt build`.
Composer, Airflow gerenciado, Cloud Workflows/Scheduler ou Dagster
adicionariam infraestrutura, IAM e custo sem necessidade demonstrável.
O projeto precisa ser executado manualmente e de forma reproduzível no
portfólio.

## Alternativas consideradas

1. GitHub Actions com `workflow_dispatch` e `concurrency`.
2. Cloud Workflows + Cloud Scheduler.
3. Cloud Composer/Airflow gerenciado.
4. Dagster ou Prefect local.
5. Execução apenas manual na máquina do desenvolvedor.

## Decisão

Usar GitHub Actions como orquestrador do MVP, com `workflow_dispatch` e
aprovação por environment. A sequência é controlada por um comando único
que executa ingestão, carga Bronze e `dbt build`.

- `workflow_dispatch` recebe parâmetros como entidade, data, modo e
  `full_refresh`.
- Um grupo de `concurrency` impede execuções simultâneas do mesmo fluxo.
- O environment de demonstração exige aprovação humana.
- Autenticação na GCP usa WIF/OIDC, sem chave JSON.
- Não há agendamento automático no MVP.
- Artefatos do dbt e logs são publicados no workflow.
- dbt não é o orquestrador; ele executa apenas as transformações.

## Consequências

- Não há custo de serviço de orquestração; o custo é o tempo de CI.
- O histórico de execuções fica no GitHub, não em uma UI de orquestração.
- Retries, dependências e SLAs são limitados ao que o workflow oferece.
- Execuções longas dependem dos limites do GitHub Actions.
- O runbook deve documentar execução manual, reprocessamento e falhas.
- Se agendamento ou SLA se tornarem requisitos, reavaliar Cloud
  Workflows ou um orquestrador dedicado.

## Critérios de reversão

Adotar um orquestrador dedicado quando houver necessidade de agendamento
recorrente, dependências complexas, retries por etapa, backfills
frequentes ou SLA operacional.
