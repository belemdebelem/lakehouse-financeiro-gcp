# Arquitetura do MVP

## Objetivo e escopo

Lakehouse batch para demonstrar ingestão, ELT, qualidade, segurança e
operação com dados inteiramente sintéticos. A execução é manual e usa
volumes pequenos. Não há streaming, serviço de computação sempre ligado
ou dado financeiro/pessoal real.

## Fluxo

```mermaid
flowchart LR
    CSV[CSV sintéticos] --> PY[Python: validar e ingerir]
    PY --> GCS[GCS: landing/raw]
    GCS --> BQLOAD[Carga batch]
    BQLOAD --> BR[BigQuery: bronze]
    BR --> SI[BigQuery: silver via dbt]
    SI --> GO[BigQuery: gold via dbt]

    TF[Terraform] -. provisiona .-> GCS
    TF -. provisiona .-> BR
    TF -. provisiona .-> SI
    TF -. provisiona .-> GO
    PY -. logs estruturados .-> LOG[Cloud Logging]
    LOG -. alerta de falha .-> MON[Cloud Monitoring]
    GH[GitHub Actions: CI, dbt build e verificações] -. OIDC/WIF .-> GCP[GCP]
```

## Camadas e responsabilidades

| Camada | Serviço | Conteúdo |
|---|---|---|
| Landing/Raw | GCS | CSV de origem preservados, identificados por entidade, data e lote. |
| Bronze | BigQuery | Linhas carregadas próximas à origem, com `batch_id`, `source_file` e `ingested_at`. |
| Silver | BigQuery + dbt | Tipos padronizados, deduplicação determinística, validações e dados rejeitados contabilizados. |
| Gold | BigQuery + dbt | Indicadores pequenos voltados às perguntas analíticas abaixo. |
| Transformação | dbt-core | Modelos SQL versionados, testes, contratos, docs e lineage. |
| Operação | BigQuery `ops` | Estado de lote (`STARTED`, `SUCCEEDED`, `FAILED`) e contagens; uma tabela simples quando o pipeline for implementado. |

O pipeline Python valida arquivos, calcula checksum e identidade estável
do lote, envia arquivos ao GCS e dispara cargas batch na Bronze. O
dbt-core executa as transformações Silver e Gold com modelos
versionados, testes e lineage. A repetição do mesmo arquivo mantém o
mesmo `batch_id` e deve ser idempotente.

## Transformações com dbt

- dbt-core + dbt-bigquery processam Silver e Gold; a Bronze é carregada
  pelo Python.
- `sources.yml` aponta para `bronze.customers`, `bronze.contracts` e
  `bronze.installments`.
- Modelos Silver são incrementais com `merge`, `unique_key`,
  particionamento, clustering e janela de segurança para dados que
  chegam atrasados; modelos Gold usam a materialização adequada a cada
  pergunta analítica.
- Testes genéricos e singulares, `store_failures`, `source freshness`,
  contratos nos marts e `dbt docs` fazem parte do fluxo.
- `profiles.yml` não contém segredos; usa ADC local e WIF/ADC no GitHub
  Actions.
- dbt não orquestra: o pipeline Python e o GitHub Actions controlam a
  ordem ingestão → Bronze → `dbt build`.
- dbt Cloud, Semantic Layer e Mesh ficam fora do MVP.

## Perguntas analíticas do MVP

1. Qual o valor original de contratos ativos no fechamento de cada mês,
   por produto? Para manter a regra simples e explícita, isso será uma
   aproximação baseada no principal original e nas datas/status do
   contrato, não um cálculo de saldo amortizado.
2. Quantas parcelas estão vencidas e não pagas, qual o valor em atraso e
   como isso varia por mês e produto?
3. Como o valor pago e a quantidade de parcelas pagas variam ao longo do
   tempo?

## Dados de entrada

- CSV UTF-8, cabeçalhos em `snake_case`, separador vírgula, datas ISO
  `YYYY-MM-DD` e decimais com ponto.
- Um arquivo por entidade e lote. Os arquivos de demonstração são
  pequenos e gerados localmente com seed fixa.
- Entidades: clientes fictícios, contratos e parcelas/pagamentos.
- Não gerar CPF, nome, endereço, conta bancária, credenciais ou valores
  obtidos de operações reais.

## Recursos GCP propostos

- Projeto GCP dedicado ao portfólio, com faturamento já associado; o
  `project_id` será fornecido antes da Fase 3.
- Região proposta: `southamerica-east1` (São Paulo), usando a mesma
  localização para o bucket e os datasets para reduzir transferências
  entre regiões e manter os dados perto do usuário.
- Um bucket regional GCS Standard para Landing/Raw, acesso uniforme,
  prevenção de acesso público e limpeza curta dos dados de demonstração.
  Versionamento de objetos fica desligado; a aplicação evita
  sobrescritas com precondição de geração.
- Datasets BigQuery `bronze`, `silver`, `gold` e `ops` na região do
  bucket. Cargas batch; consultas sob demanda com limite de bytes
  processados; sem reservas de slots.
- dbt-core roda localmente e no GitHub Actions; não há serviço GCP
  adicional nem custo de licença. O custo é o tempo de CI e os bytes
  processados no BigQuery.
- Cloud Logging para logs estruturados do pipeline, com baixo volume e
  retenção padrão.
- Cloud Monitoring para métricas nativas e um alerta simples de falha
  baseado em logs. Sem uptime checks, dashboards amplos ou métricas
  customizadas de alta cardinalidade no MVP.
- IAM com menor privilégio. ADC na execução local; Workload Identity
  Federation para GitHub Actions quando o CD for implementado. Nenhuma
  chave JSON de service account no repositório.
- Secret Manager permanece disponível para um segredo real caso surja
  essa necessidade. ADC/WIF evitam criar segredo estático para a
  autenticação normal do MVP; não criar segredo de demonstração fictício.
- Terraform para os recursos. O state remoto restrito será avaliado na
  Fase 3/8; se necessário, seu pequeno custo e o bootstrap serão
  explicitados no plano antes da criação.

## Controles de custo

- Orçamento mensal sugerido: menor valor aceito pela Console, usando
  equivalente a US$ 1 como referência, com alertas em 50%, 90% e 100%.
  Esse orçamento alerta; não interrompe o consumo.
- Execuções manuais, poucos CSVs sintéticos e sem recursos ociosos.
- Manter GCS e BigQuery na mesma região. Não usar streaming, Dataflow,
  Cloud Run, VMs, Scheduler ou reservas de slots no MVP.
- Revisar Billing após a demonstração e remover dados/recursos que não
  precisam permanecer.
- Estimativa de planejamento: aproximadamente US$ 0,01–0,10 por mês para
  armazenamento/uso pequeno em São Paulo, supondo até 1 GiB no GCS,
  consultas e logs muito abaixo das franquias gratuitas e sem state
  remoto adicional. O valor final depende de volume, região, franquias
  compartilhadas na conta, câmbio e impostos.

## Segurança, logging e monitoramento

- Gitleaks verifica segredos no repositório; Checkov verifica Terraform;
  IAM reduz permissões; ADC/WIF evitam chaves duradouras.
- O `profiles.yml` do dbt não contém segredos e usa ADC/WIF; os artefatos
  do dbt não incluem credenciais.
- Cada log de pipeline inclui `pipeline_name`, `batch_id`, `source_file`,
  `stage`, `status`, timestamps e contagens disponíveis. Mensagens não
  incluem credenciais nem dados sensíveis.
- Cloud Logging recebe os logs explicitamente; scripts locais e GitHub
  Actions não enviam logs automaticamente.
- Cloud Monitoring usa métricas nativas do BigQuery/GCP e um alerta de
  falha baseado em logs. Métricas customizadas só serão adicionadas se
  forem necessárias e após avaliar custo/cardinalidade.

## Fora do MVP

Streaming, Dataflow/Beam, Pub/Sub, Composer, Scheduler/Workflows,
Dataplex, dbt Cloud/Semantic Layer/Mesh, dashboard próprio, Kubernetes,
APIs bancárias reais e dados pessoais reais.

## Decisões relacionadas

- [ADR 0001 — Arquitetura MVP, segurança e custo](decisions/0001-arquitetura-mvp-e-custos.md)
- [ADR 0002 — dbt-core para Silver e Gold](decisions/0002-dbt-para-silver-e-gold.md)
- [ADR 0003 — GitHub Actions como orquestrador do MVP](decisions/0003-orquestracao-github-actions.md)
- [ADR 0004 — Segurança automatizada mínima](decisions/0004-seguranca-automatizada-minima.md)
- [ADR 0005 — State local do Terraform no MVP](decisions/0005-estado-local-terraform.md)
