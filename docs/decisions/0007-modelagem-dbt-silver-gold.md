# ADR 0007 — Modelagem dbt Silver e Gold com isolamento por target

- **Status:** aceita para a Fase 6
- **Data:** 2026-11-19

## Contexto

A Fase 5 carregou os CSVs sintéticos na Bronze com metadados de lote. A
Fase 6 precisa transformar esses dados em camadas Silver e Gold dentro do
BigQuery, com tipos padronizados, deduplicação determinística,
incrementalidade, regras analíticas e testes versionados. Execuções de
desenvolvimento não podem sobrescrever as tabelas de demonstração de
`silver` e `gold`.

## Decisão

O projeto usa `dbt-core==1.12.6` com `dbt-bigquery==1.12.3`, fixados juntos
no `pyproject.toml` e no `uv.lock`. Não há dbt packages externos nesta
fase.

`profiles.yml` não contém segredos: usa `env_var`, ADC (`method: oauth`),
`maximum_bytes_billed` e dois targets, `dev` e `prod`. O target padrão vem
de `DBT_TARGET`. A macro `generate_schema_name` mantém `silver`/`gold` para
`prod` e redireciona os demais targets para `silver_dev`/`gold_dev`. O
Terraform cria esses datasets e concede `roles/bigquery.dataEditor` na
conta de serviço `lakehouse-dbt`.

Modelos Silver são incrementais com `merge`, `unique_key`, partição por
`updated_at`, clustering por colunas de filtro, janela de segurança de
3 dias via `late_arrival_days` e deduplicação por `updated_at`,
`ingested_at` e `source_file`. Contratos de modelo são enforcement apenas
na Silver; Gold usa `table` sem contrato enforcement nesta fase.

As regras analíticas adotadas foram:

- `as_of_date` padrão `2026-01-31`.
- `mart_carteira_credito`: principal original de contratos `active` ou
  `closed` cujo intervalo `start_date`–`end_date` cobre o fim do mês de
  referência; `cancelled` fica fora.
- `mart_inadimplencia`: parcelas com `due_date` anterior à data de
  referência, sem pagamento integral até essa data e com status `open` ou
  `overdue`.
- `fato_pagamentos`: parcelas com `paid_at` não nulo, incluindo dias entre
  vencimento e pagamento.

Testes genéricos cobrem `unique`, `not_null`, `relationships` e
`accepted_values`. Testes singulares verificam unicidade composta, datas
de contrato, valores de parcela, data de pagamento e chaves dos marts.
`dbt docs generate` produz `catalog.json` e lineage no target local.

## Alternativas consideradas

- **Escrever SQL solto no BigQuery:** mais simples, mas sem versionamento,
  testes, lineage nem contratos.
- **Usar somente o schema `silver`/`gold` para todos os targets:** exigiria
  limpar tabelas entre execuções e aumentaria o risco de sobrescrever a
  demonstração.
- **Contratos enforcement também na Gold:** daria falha rápida em mudanças
  de coluna, mas os marts ainda estão evoluindo; a regra atual evita
  rigidez prematura onde o benefício é menor.
- **dbt Cloud ou packages externos:** não são necessários para o volume e
  o escopo do MVP.

## Consequências

- `dbt build --target dev` é seguro para iteração e não altera `silver` ou
  `gold`.
- O `require-dbt-version` usa `[">=1.12.0", "<2.0.0"]`; dbt rejeita `<2.0`
  por não ser uma versão semântica completa.
- Modelos incrementais com contratos precisam declarar `on_schema_change`;
  a opção escolhida foi `fail`, para interromper execuções quando o schema
  mudar.
- `store_failures`, `dbt source freshness` e `ops.dq_results` permanecem
  como evoluções previstas para a Fase 7.
- A reexecução do mesmo `dbt build` não duplica dados porque a Silver usa
  `merge` e a Gold usa tabelas recreáveis.
