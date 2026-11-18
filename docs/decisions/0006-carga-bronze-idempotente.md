# ADR 0006 — Carga idempotente para a Bronze

- **Status:** aceita para a Fase 5
- **Data:** 2026-11-17

## Contexto

A Fase 4 preservou os CSVs no GCS e gravou `batch_id`, `sha256` e
`ingested_at` como metadados dos objetos. A Fase 5 precisa carregar esses
arquivos na Bronze sem duplicar registros quando o lote for reexecutado,
sem inferir schema permanentemente e com rastreabilidade do estado do
lote.

## Decisão

O Terraform continua responsável apenas pelos datasets. Tabelas Bronze,
staging e `ops.ingestion_batches` são criadas por DDL versionado em
`sql/`, que é a única fonte de verdade para esses recursos.

Cada entidade é carregada primeiro em `bronze.<entidade>_staging` com
`WRITE_TRUNCATE` e schema explícito. Em seguida, um `MERGE` atualiza ou
insere na tabela final pela chave de negócio, acrescentando `batch_id`,
`source_file`, `ingested_at` e `ingestion_date`. Antes do processamento,
`ops.ingestion_batches` registra `STARTED`; ao final, `SUCCEEDED`; em caso
de falha, `FAILED` com a mensagem de erro.

## Alternativas consideradas

- **`WRITE_APPEND` direto na Bronze:** simples, mas duplicaria linhas em
  qualquer reexecução e não permitiria marcar falhas com controle
  adicional.
- **Tabelas externas sobre o GCS:** evitaria cópia, mas deixaria o
  contrato de schema dependente de metadados do objeto e não permitiria
  enriquecer linhas com metadados do lote da forma desejada.
- **Criar tabelas com Terraform:** misturaria DDL analítico com
  infraestrutura e exigiria representar colunas e partições em HCL.

## Consequências

- Reexecução do mesmo `batch_id` é ignorada quando o lote já está
  `SUCCEEDED` em `ops`.
- Falhas parciais não são marcadas como sucesso; o `MERGE` é determinístico
  pela chave de negócio, permitindo repetir a carga após correção.
- A tabela `ingestion_date` particiona a Bronze e o cluster usa colunas de
  filtro usuais, com custo controlado por ser um volume pequeno.
- Alterações de schema exigem editar o DDL versionado e o schema em código
  no mesmo commit.
