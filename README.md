# Financial Data Lakehouse --- GCP

> **Guia de implementação para uma LLM em CLI**
>
> Este documento é a especificação de trabalho do projeto. Implemente-o
> de forma incremental, seguindo as fases na ordem definida. **Não tente
> construir toda a arquitetura de uma vez.** Ao concluir cada fase,
> apresente o que foi feito, os arquivos alterados, os testes
> executados, as decisões tomadas e os próximos passos. Aguarde
> autorização explícita antes de iniciar a fase seguinte.

------------------------------------------------------------------------

## 1. Visão geral

Construir um Lakehouse financeiro na **Google Cloud Platform (GCP)**
para ingerir, armazenar, transformar e disponibilizar dados sintéticos
de operações de crédito e pagamentos.

O projeto deve demonstrar competências práticas de:

-   Engenharia de Dados: ingestão batch, ELT, modelagem,
    incrementalidade, idempotência e qualidade.
-   DataOps: padronização, versionamento, testes e rastreabilidade dos
    pipelines.
-   DevOps: infraestrutura como código e CI/CD.
-   DevSecOps: gestão segura de credenciais, menor privilégio e
    verificações automatizadas.
-   Observabilidade: logs, métricas e alertas úteis para operação.

O projeto é voltado a **portfólio profissional e apresentação técnica em
evento**. A prioridade é uma arquitetura pequena, compreensível,
reproduzível e tecnicamente defensável --- não a quantidade de serviços
utilizados.

### 1.1 Princípios de implementação

1.  **Uma fase por vez.** Não avance sem validação do usuário.
2.  **Simplicidade primeiro.** Adicione componentes somente quando
    houver uma necessidade demonstrável.
3.  **Serviços gerenciados.** Evite administrar infraestrutura que a GCP
    já oferece como serviço.
4.  **Batch e ELT no MVP.** Não implementar streaming nesta versão.
5.  **Segurança desde o início.** Nunca inserir credenciais no código,
    nos arquivos de configuração versionados ou nos logs.
6.  **Reprodutibilidade.** Um desenvolvedor deve conseguir entender e
    reproduzir o projeto seguindo a documentação.
7.  **Custos controlados.** Usar volumes pequenos, consultas econômicas
    e recursos que possam ser desligados ou removidos.
8.  **Decisões explícitas.** Registrar decisões arquiteturais relevantes
    em `docs/decisions/`.
9.  **Código proporcional ao problema.** Evitar abstrações, frameworks e
    camadas desnecessárias.
10. **Sem funcionalidades fictícias.** Documentar somente o que estiver
    implementado e testado.
11. **GCP com custo mínimo.** Usar os serviços previstos em volumes
    pequenos e sob demanda; revisar custos antes de criar recursos e
    evitar componentes ociosos ou opcionais.

------------------------------------------------------------------------

## 2. Escopo e limites

### 2.1 Dentro do escopo

-   Dados sintéticos de clientes, contratos de crédito e pagamentos.
-   Ingestão batch por scripts Python.
-   Armazenamento inicial de arquivos no Google Cloud Storage (GCS).
-   Carga dos dados no BigQuery.
-   Camadas Bronze, Silver e Gold no BigQuery.
-   Transformações ELT com SQL, modeladas e executadas pelo dbt-core
    entre Bronze e Gold.
-   Projeto dbt versionado para Silver e Gold, com testes, contratos,
    incrementalidade e documentação de lineage.
-   Processamento incremental, deduplicação e idempotência.
-   Validações de qualidade e testes automatizados.
-   Infraestrutura GCP provisionada com Terraform.
-   CI/CD com GitHub Actions.
-   Segurança com IAM, ADC/WIF, Secret Manager quando houver segredo
    necessário, Gitleaks e Checkov.
-   Logs estruturados no Cloud Logging e monitoramento operacional no
    Cloud Monitoring, dimensionados para baixo volume.
-   Documentação da arquitetura, execução, custos e decisões.

### 2.2 Fora do escopo do MVP

Não implementar nesta primeira versão:

-   Apache Beam ou Dataflow.
-   Pub/Sub ou ingestão streaming.
-   Dataplex.
-   Cloud Composer / Airflow.
-   Cloud Scheduler ou Workflows.
-   dbt Cloud, dbt Semantic Layer e dbt Mesh.
-   Aplicação web, API própria ou dashboard customizado.
-   Kubernetes ou microsserviços.
-   Integração com dados bancários reais, dados pessoais reais ou APIs
    que exijam credenciais desnecessárias.

Esses itens não são necessários para demonstrar o objetivo central.
Streaming ou outros serviços poderão ser avaliados em uma evolução
futura, mediante justificativa técnica e análise de custo.

------------------------------------------------------------------------

## 3. Arquitetura-alvo

### 3.1 Fluxo lógico

``` text
Dados sintéticos (CSV ou Parquet)
              |
              v
       Python — Ingestão
              |
              v
 Google Cloud Storage (GCS)
       landing / raw
              |
              v
       BigQuery — Bronze
       dados carregados + metadados
              |
              v
       dbt-core — Silver
       padronização, deduplicação,
       validação e incrementalidade
              |
              v
       dbt-core — Gold
       modelos e indicadores financeiros
```

A infraestrutura e a operação são transversais ao fluxo:

``` text
Terraform ──> recursos GCP e IAM
Git/GitHub ──> versionamento e revisão
GitHub Actions ──> testes, segurança e implantação
dbt ──> transformações, testes e lineage
Gitleaks ──> detecção de segredos
Checkov ──> análise estática do Terraform
Secret Manager ──> segredos que realmente forem necessários
Cloud Logging ──> logs de execução
Cloud Monitoring ──> métricas e alertas
Docker ──> ambiente local reproduzível, quando necessário
```

### 3.2 Decisão: ELT no BigQuery

O projeto utilizará **ELT**: extrair e carregar os dados primeiro;
realizar as transformações analíticas depois, dentro do BigQuery, usando
SQL.

-   Python será responsável pela ingestão, validações de arquivo,
    metadados de lote, carga na Bronze e interação com GCS/BigQuery.
-   GCS será a área de aterrissagem e preservação dos arquivos
    originais.
-   BigQuery será o ambiente de armazenamento analítico.
-   dbt-core será responsável pelas transformações Silver e Gold, com
    modelos SQL versionados, testes, contratos e documentação de lineage.
-   O pipeline Python e o GitHub Actions preparam a Bronze e disparam o
    `dbt build`; o dbt não é o orquestrador da sequência.

Não adicionar Dataflow/Beam apenas para tornar a arquitetura
aparentemente mais sofisticada. Eles resolvem necessidades de
processamento distribuído e streaming que não fazem parte do MVP.

### 3.3 Camadas Medallion

  -----------------------------------------------------------------------
  Camada                  Local                   Responsabilidade
  ----------------------- ----------------------- -----------------------
  Landing/Raw             GCS                     Preservar os arquivos
                                                  recebidos sem
                                                  sobrescrever o
                                                  original.

  Bronze                  BigQuery                Dados carregados
                                                  próximos ao formato de
                                                  origem, com metadados
                                                  de ingestão.

  Silver                  BigQuery + dbt          Dados tipados,
                                                  padronizados,
                                                  deduplicados e
                                                  validados.

  Gold                    BigQuery + dbt          Tabelas analíticas
                                                  orientadas a perguntas
                                                  de negócio.
  -----------------------------------------------------------------------

**Importante:** GCS Landing/Raw não substitui a Bronze. A Bronze será a
primeira camada tabular carregada no BigQuery. Evitar cópias
desnecessárias: cada camada deve ter uma finalidade clara.

### 3.4 Domínio de dados

Usar dados sintéticos e consistentes de:

-   Clientes fictícios: identificador técnico, segmento e atributos não
    identificáveis.
-   Contratos: identificador, cliente, produto, valor, taxa, datas e
    status.
-   Parcelas/pagamentos: contrato, número da parcela, vencimento,
    pagamento, valor e situação.
-   Indicadores econômicos: série temporal sintética, se houver uma
    necessidade analítica clara.

Não utilizar CPF, nome, endereço, conta bancária ou qualquer dado real.
Se for necessário um identificador com aparência de documento, gerar
valor fictício e claramente não válido.

### 3.5 Produtos analíticos

Começar com um conjunto pequeno de tabelas Gold, por exemplo:

-   `gold.mart_carteira_credito`: posição da carteira por período e
    produto.
-   `gold.mart_inadimplencia`: parcelas vencidas, valores em atraso e
    indicadores por período.
-   `gold.fato_pagamentos`: pagamentos consolidados para análise
    temporal.

Não criar todas as dimensões e fatos antecipadamente. Definir o modelo a
partir das perguntas analíticas que o projeto pretende responder.

------------------------------------------------------------------------

## 4. Tecnologias e responsabilidades

  -----------------------------------------------------------------------
  Tecnologia                          Uso definido no projeto
  ----------------------------------- -----------------------------------
  Python                              Ingestão batch, validação de
                                      arquivos, controle de lotes,
                                      carga na Bronze e operação.

  Google Cloud Storage                Armazenar arquivos de origem na
                                      área Landing/Raw.

  BigQuery                            Camadas Bronze, Silver e Gold;
                                      armazenamento, SQL analítico e
                                      tabelas de controle.

  dbt-core / dbt-bigquery             Modelos Silver e Gold, testes,
                                      contratos, incrementalidade,
                                      lineage e documentação.

  SQL                                 Modelos dbt, transformações,
                                      deduplicação, regras de negócio
                                      e testes de dados.

  Terraform                           Provisionar recursos GCP e
                                      permissões como código.

  Git                                 Controle de versão local.

  GitHub                              Repositório, pull requests, issues
                                      e documentação.

  GitHub Actions                      CI de testes e verificações; CD
                                      controlado para infraestrutura e
                                      pipeline.

  Docker                              Padronizar o ambiente de
                                      desenvolvimento/testes se isso
                                      reduzir diferenças entre ambientes.
                                      Não é obrigatório executar o
                                      pipeline em container na primeira
                                      versão.

  Gitleaks                            Detectar segredos acidentalmente
                                      adicionados ao repositório.

  Checkov                             Verificar configurações inseguras
                                      nos arquivos Terraform.

  IAM                                 Aplicar menor privilégio a usuários
                                      e contas de serviço.

  Secret Manager                      Gerenciar segredos necessários;
                                      preferir ADC/WIF para evitar chaves
                                      estáticas. Não criar segredo fictício.

  Cloud Logging                       Receber logs estruturados do
                                      pipeline, com baixo volume e
                                      retenção padrão curta.

  Cloud Monitoring                    Acompanhar métricas nativas e
                                      alertar falhas do pipeline com
                                      poucas séries de baixa cardinalidade.
  -----------------------------------------------------------------------

### 4.1 Ferramentas e serviços deliberadamente não utilizados

-   **Dataflow/Beam:** processamento distribuído não é necessário para o
    volume e o padrão batch do MVP.
-   **Pub/Sub:** não há fluxo de eventos em tempo real no escopo atual.
-   **dbt Cloud, dbt Semantic Layer e dbt Mesh:** o MVP usa apenas
    dbt-core local/CI; recursos pagos ou de governança avançada não são
    necessários.
-   **Cloud Composer:** não há necessidade de uma plataforma Airflow
    para poucas etapas batch.
-   **Cloud Scheduler/Workflows:** o MVP pode ser executado manualmente
    e por workflow_dispatch do GitHub Actions. Agendamento não é
    requisito inicial.
-   **Dataplex:** governança corporativa avançada não é necessária para
    o escopo demonstrativo.
-   **Bandit, pip-audit e Trivy:** não fazem parte do conjunto mínimo de
    segurança definido; a decisão e os riscos aceitos estão registrados
    em `docs/decisions/0004-seguranca-automatizada-minima.md`. Não
    instalar ferramentas adicionais sem uma justificativa concreta.

------------------------------------------------------------------------

## 5. Requisitos técnicos não funcionais

### 5.1 Incrementalidade

O pipeline deve identificar novos registros e alterações sem recarregar
indiscriminadamente todo o histórico.

-   Definir uma chave de negócio ou chave técnica estável para cada
    entidade.
-   Definir, quando aplicável, um campo de atualização (`updated_at`) ou
    estratégia equivalente.
-   Manter metadados de lote, como `batch_id`, `source_file`,
    `ingested_at` e, quando útil, checksum.
-   Implementar modelos incrementais no dbt com
    `incremental_strategy='merge'`, `unique_key`, particionamento e
    clustering.
-   Usar `updated_at` como `TIMESTAMP` UTC e uma janela de segurança
    para dados que chegam atrasados; `ingested_at` serve como desempate.
-   Usar `MERGE` gerado pelo dbt ou SQL explícito para inserir novos
    registros e atualizar registros existentes conforme regra clara.
-   Documentar como exclusões na origem seriam tratadas; não presumir
    que ausência em um arquivo significa exclusão.

### 5.2 Idempotência

Executar o mesmo lote novamente não pode gerar duplicidades ou
resultados diferentes sem justificativa.

-   Definir identidade estável para o lote.
-   Registrar status e metadados de ingestão em uma tabela operacional,
    por exemplo `ops.ingestion_batches`.
-   Controlar transições de status, como `STARTED`, `SUCCEEDED` e
    `FAILED`.
-   Fazer operações de carga e transformação de forma repetível;
    reexecutar `dbt build` do mesmo lote não pode duplicar registros.
-   Não marcar um lote como concluído antes de todas as etapas
    obrigatórias terminarem.
-   Testar explicitamente a reexecução do mesmo arquivo.

Não implementar mecanismos complexos de transação distribuída. Preferir
operações idempotentes no BigQuery e estados operacionais simples.

### 5.3 Qualidade dos dados

Começar com regras objetivas:

-   Campos obrigatórios não nulos.
-   Identificadores únicos conforme a granularidade definida.
-   Datas válidas e coerentes.
-   Valores monetários dentro de limites plausíveis.
-   Relacionamentos válidos entre contratos e pagamentos.
-   Ausência de pagamentos associados a contratos inexistentes.
-   Regras de domínio para status e tipos de produto.
-   Testes genéricos do dbt: `unique`, `not_null`, `relationships` e
    `accepted_values`.
-   Testes singulares do dbt para datas, valores e regras de negócio.
-   `dbt source freshness` na Bronze e `store_failures` para persistir
    falhas.

Registros inválidos devem ser contabilizados e, quando possível,
isolados em uma área/tabela de rejeitados. Não descartar dados
silenciosamente.

### 5.4 Particionamento e custo

-   Particionar tabelas grandes por uma coluna de data adequada à
    consulta.
-   Usar clustering somente quando houver padrão de filtro/agrupamento
    que o justifique.
-   Evitar `SELECT *` em transformações e consultas analíticas.
-   Definir limites de bytes processados em consultas quando aplicável.
-   Preferir datasets e tabelas pequenos durante o desenvolvimento.
-   Configurar no Cloud Billing um orçamento mensal para este projeto no
    menor valor aceito pela Console (sugestão inicial: equivalente a
    **US$ 1**), com alertas em 50%, 90% e 100% do gasto real e envio ao
    responsável pelo projeto. O valor deve ser revisado se a Console
    exigir outro mínimo ou se a moeda da conta for diferente.
-   Tratar o orçamento como alerta, nunca como limite de gasto: alertas
    de orçamento não bloqueiam automaticamente serviços nem cobranças.
    Verificar Billing Reports após as sessões de uso.
-   Executar o pipeline manualmente e somente quando necessário. Não
    configurar agendamento automático no MVP; não deixar recursos
    computacionais ligados ou criar serviços opcionais sem necessidade
    demonstrável.
-   Executar `dbt build` completo apenas em execução manual ou na branch
    principal; em pull requests, preferir `dbt parse`, `dbt compile` e
    `sqlfluff` para reduzir tempo e custo.
-   dbt-core é open source e roda localmente/CI; não há serviço GCP
    adicional nem licença. O custo é o tempo de CI e os bytes
    processados no BigQuery.
-   Usar arquivos sintéticos pequenos, tabelas compactas, consultas com
    colunas e filtros explícitos e limites de bytes processados quando
    disponíveis. Evitar consultas exploratórias repetidas e `SELECT *`.
-   Usar uma única região compatível para bucket e datasets sempre que
    possível; evitar replicação multirregional e transferências entre
    regiões. Definir retenção curta para dados de demonstração e
    documentar a limpeza dos recursos.
-   Antes de habilitar um serviço, conferir preço e nível gratuito
    aplicável à conta e à região. Não presumir custo zero por estar
    abaixo de limites gratuitos, pois esses limites podem variar e o
    excedente pode ser cobrado.
-   Enviar logs estruturados do pipeline ao Cloud Logging e usar métricas
    nativas do BigQuery/Cloud Monitoring. Manter baixo volume, retenção
    padrão e sem sinks para outros destinos no MVP.
-   Criar somente os alertas operacionais necessários para a
    demonstração, preferindo alertas baseados em logs e métricas nativas.
    Evitar métricas customizadas com labels de alta cardinalidade, como
    `batch_id`, pois aumentam a quantidade de séries monitoradas.
-   Conferir os níveis gratuitos e preços atuais de Logging/Monitoring
    antes da implantação e acompanhar o uso faturável. Os limites e
    preços podem mudar; excedentes podem ser cobrados.
-   Documentar como excluir recursos e evitar custos recorrentes.

### 5.5 Observabilidade

Cada execução deve produzir logs estruturados com, no mínimo:

-   `pipeline_name`
-   `batch_id`
-   `source_file`
-   `stage`
-   `status`
-   `started_at` e `finished_at`
-   quantidade de registros lidos, carregados, rejeitados e afetados,
    quando disponível
-   mensagem de erro sem expor segredos ou dados sensíveis
-   artefatos do dbt (`run_results.json`, `manifest.json`) usados para
    contagens, status e diagnóstico

Criar alertas proporcionais ao projeto, por exemplo para falha de
execução ou ausência de uma execução esperada quando houver agendamento
no futuro. Não criar dashboards ou métricas sem uma pergunta operacional
clara.

------------------------------------------------------------------------

## 6. Estrutura sugerida do repositório

Ajustar a estrutura somente quando houver necessidade real. Não criar
diretórios vazios para tecnologias ainda não implementadas.

``` text
financial-data-lakehouse/
├── README.md
├── pyproject.toml
├── uv.lock                       # lockfile reproduzível; não editar manualmente
├── .env.example                  # somente nomes de variáveis, sem valores reais
├── .gitignore
├── Dockerfile                    # adicionar quando o container tiver uso definido
├── src/
│   └── lakehouse/
│       ├── config/
│       ├── ingestion/
│       ├── storage/
│       ├── bigquery/
│       ├── pipeline/
│       └── observability/
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml              # sem segredos; usa env_var e ADC
│   ├── models/
│   │   ├── sources.yml
│   │   ├── silver/
│   │   └── gold/
│   ├── macros/
│   ├── tests/
│   └── snapshots/
├── sql/
│   ├── ddl/                      # bronze e ops, se não provisionados via Terraform
│   └── adhoc/                    # consultas manuais, sem resultados versionados
├── data/
│   ├── sample/                   # amostras pequenas e sintéticas
│   └── generated/                # ignorar dados gerados volumosos
├── tests/
│   ├── unit/
│   └── integration/
├── infrastructure/
│   └── terraform/
│       ├── modules/
│       ├── environments/
│       └── README.md
├── scripts/
├── .github/
│   └── workflows/
├── docs/
│   ├── architecture.md
│   ├── data-dictionary.md
│   ├── runbook.md
│   └── decisions/
└── Makefile                       # opcional, apenas para comandos repetidos
```

**Decisão de dependências:** preferir `pyproject.toml` como fonte
principal de configuração e dependências, com lockfile gerado (por
exemplo, `uv.lock`). Não manter dois arquivos independentes com listas
divergentes. Pinar `dbt-core` e `dbt-bigquery` para garantir
compatibilidade. Evitar dbt packages externos sem necessidade real.

------------------------------------------------------------------------

## 7. Plano de implementação por fases

A LLM deve seguir esta sequência. Cada fase tem objetivo, tarefas,
critérios de aceite e uma condição de parada.

Os artefatos da Fase 1 não são congelados: cada fase seguinte atualiza
`pyproject.toml`, `uv.lock`, `.env.example`, `Settings`, testes,
`.gitignore` e `docs/dev/setup.md` no mesmo commit da feature, conforme
`docs/dev/fase1-evolucao.md`.

### Fase 0 --- Alinhamento e desenho (concluída)

**Objetivo:** fechar o escopo antes de escrever código.

Tarefas:

1.  Confirmar o domínio e as entidades sintéticas.
2.  Definir as perguntas analíticas que as tabelas Gold responderão.
3.  Definir granularidade e chaves de clientes, contratos e pagamentos.
4.  Definir formato dos arquivos de entrada.
5.  Validar o fluxo Landing → Bronze → Silver → Gold.
6.  Identificar recursos GCP e estimar custos/risco de cobrança para um
    volume pequeno de demonstração; verificar níveis gratuitos atuais,
    sem tratá-los como garantia de custo zero.
7.  Registrar as decisões iniciais em `docs/decisions/`.

**Aceite:**

-   Diagrama simples da arquitetura.
-   Dicionário inicial de dados.
-   Lista de recursos GCP.
-   Escopo do MVP e itens explicitamente adiados.
-   Decisões registradas e explicadas.

**Parar e pedir aprovação.** Não criar infraestrutura nem código de
pipeline nesta fase.

### Fase 1 --- Repositório e ambiente local (concluída)

**Objetivo:** criar uma base de desenvolvimento reproduzível.

Tarefas:

1.  Criar a estrutura mínima do repositório.
2.  Configurar Python e dependências.
3.  Definir estilo, formatação e linting de forma proporcional.
4.  Configurar `pytest`.
5.  Criar `.gitignore` e `.env.example`.
6.  Documentar instalação e execução local.
7.  Criar um teste simples para validar o ambiente.
8.  Registrar em `docs/dev/fase1-evolucao.md` o contrato de atualização
    dos artefatos da Fase 1 pelas fases seguintes.

**Aceite:**

-   Instalação reproduzível em ambiente limpo.
-   Testes executados localmente.
-   Nenhuma credencial ou dado sensível versionado.
-   README de desenvolvimento atualizado.
-   Contrato de evolução registrado e referenciado nas fases seguintes.

**Parar e pedir aprovação.**

### Fase 2 --- Dados sintéticos e contrato de dados (concluída)

**Objetivo:** definir entradas consistentes para os pipelines.

Tarefas:

1.  Criar gerador determinístico de dados sintéticos.
2.  Gerar arquivos pequenos de clientes, contratos e pagamentos.
3.  Definir esquema, tipos, campos obrigatórios e chaves.
4.  Criar exemplos válidos e inválidos.
5.  Documentar granularidade, relacionamentos e regras de domínio.
6.  Garantir que a geração repetida com a mesma seed seja reproduzível.
7.  Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (dependências/lockfile, testes e
    `docs/dev/setup.md`).

**Aceite:**

-   Dados sem informação pessoal real.
-   Relacionamentos coerentes entre entidades.
-   Dicionário de dados e contratos documentados.
-   Testes para o gerador e para os esquemas.

**Parar e pedir aprovação.**

### Fase 3 --- Infraestrutura GCP com Terraform (concluída)

**Objetivo:** provisionar somente os recursos necessários para o MVP.

Tarefas:

1.  Definir projeto GCP, região e convenções de nomes.
2.  Configurar orçamento mensal baixo e alertas de faturamento no escopo
    do projeto; isso não bloqueia cobranças.
3.  Criar configuração Terraform mínima para um bucket GCS regional e
    datasets BigQuery necessários ao fluxo, sem recursos opcionais.
4.  Definir IAM com menor privilégio.
5.  Habilitar somente as APIs necessárias aos recursos aprovados.
6.  Definir estratégia de state do Terraform e avaliar o custo de
    armazenamento remoto antes de criar um bucket exclusivo para state.
7.  Validar `terraform fmt`, `terraform validate` e `terraform plan`.
    Revisar localização, retenção, permissões e recursos que podem gerar
    cobranças.
8.  Executar o provisionamento somente após revisão e aprovação
    explícita.
9.  Documentar destruição segura dos recursos e conferir Billing após
    cada sessão de uso.
10. Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (`.gitignore` para
    `.terraform.lock.hcl` e `docs/dev/setup.md`).

**Decisões de segurança:**

-   Não colocar chaves JSON de service account no Git.
-   Para execução local, preferir Application Default Credentials (ADC).
-   Para GitHub Actions, preferir Workload Identity Federation (OIDC) em
    vez de chave de longa duração.
-   Separar identidade de CI/deploy da identidade de execução do
    pipeline quando isso for viável.
-   Conceder apenas as permissões necessárias a cada identidade.
-   O bucket de state remoto, se utilizado, precisa de bootstrap
    controlado e permissões restritas. Não criar dependência circular
    entre o backend e o próprio Terraform.

**Aceite:**

-   `terraform plan` revisado.
-   Recursos mínimos criados e identificados.
-   IAM documentado.
-   State protegido e não versionado no repositório.
-   Procedimento de limpeza documentado.

**Resultado da execução (2026-11-17):**

-   `terraform apply` autorizado e executado a partir do plano salvo:
    `Apply complete! Resources: 22 added, 0 changed, 0 destroyed.`
-   Bucket: `lakehouse-financeiro-demo-belemdebelem` em
    `southamerica-east1`.
-   Datasets: `bronze`, `silver`, `gold` e `ops`.
-   Service accounts: `lakehouse-pipeline` e `lakehouse-dbt`.
-   Verificação posterior: `No changes. Your infrastructure matches the
    configuration.`
-   Orçamento mensal de R$ 1 já existente na conta de billing foi
    reutilizado; nenhum orçamento duplicado foi criado.

**Nunca executar `terraform apply` ou destruir recursos sem autorização
do usuário.** A autorização desta execução foi registrada acima.

### Fase 4 --- Ingestão Python para GCS (concluída)

**Objetivo:** implementar a entrada batch dos arquivos.

Tarefas:

1.  Implementar leitura e validação inicial dos arquivos.

2.  Gerar metadados de lote e checksum.

3.  Enviar os arquivos para GCS em caminho organizado, por exemplo:

    `landing/<entidade>/ingestion_date=YYYY-MM-DD/<arquivo>`

4.  Preservar arquivos originais; evitar sobrescrever objetos
    existentes.

5.  Registrar logs estruturados.

6.  Tratar erros de leitura, validação e upload.

7.  Criar testes unitários com mocks e testes de integração controlados.
8.  Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (dependência de GCS, `GCS_BUCKET_NAME`
    em `Settings`, `.env.example`, testes e `docs/dev/setup.md`).

Manter a ingestão manual, com poucos arquivos sintéticos, evitando
uploads repetidos e objetos duplicados. Definir retenção/limpeza dos
arquivos de demonstração e considerar o custo de armazenamento e de
operações do bucket.

**Aceite:**

-   Arquivos válidos enviados ao GCS.
-   Arquivos inválidos rejeitados com motivo registrado.
-   Reexecução não sobrescreve silenciosamente dados originais.
-   Logs identificam lote e arquivo.
-   Testes automatizados aprovados.

**Resultado da execução (2026-11-17):**

-   `google-cloud-storage` adicionado e `GCS_BUCKET_NAME` passou a ser
    lida por `Settings`.
-   Três objetos enviados para
    `landing/<entidade>/ingestion_date=2026-11-17/` com checksum SHA-256,
    `batch_id`, `source_file`, `ingested_at` e `row_count` nos metadados.
-   Reexecução controlada da mesma data falhou por precondição e não
    alterou o objeto original.
-   Logs incluem `pipeline_name`, `stage`, `status`, `batch_id`,
    `source_file`, `object_path`, `sha256` e contagens.
-   Testes: 19 passaram e 1 teste de integração opt-in passou contra o
    bucket real.

**Parar e pedir aprovação.**

### Fase 5 --- Carga GCS para BigQuery Bronze (concluída)

**Objetivo:** carregar os arquivos na camada Bronze.

Tarefas:

1.  Criar datasets e tabelas Bronze via Terraform ou SQL versionado,
    escolhendo uma única fonte de verdade para cada recurso.
2.  Definir esquema explícito; evitar inferência automática como
    contrato permanente.
3.  Implementar carga de GCS para BigQuery usando o cliente oficial.
4.  Adicionar metadados como `batch_id`, `source_file` e `ingested_at`.
5.  Registrar estado do lote em tabela operacional `ops`, se aprovado na
    Fase 0.
6.  Tratar falhas e reexecução sem duplicar registros.
7.  Documentar estratégia de carga e particionamento.
8.  Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (dependência do BigQuery, `BQ_DATASET_*`
    em `Settings`, `.env.example`, testes e `docs/dev/setup.md`).

Executar cargas somente sob demanda e usar o menor conjunto de dados
que demonstre o fluxo. Acompanhar bytes processados nas consultas e
evitar streaming e consultas exploratórias amplas.

**Aceite:**

-   Arquivos válidos carregados em Bronze.
-   Esquema previsível e documentado.
-   Lotes rastreáveis.
-   Reexecução do mesmo lote testada.
-   Falhas não são marcadas como sucesso.

**Resultado da execução (2026-11-17):**

-   `google-cloud-bigquery` adicionado e `BQ_DATASET_BRONZE`,
    `BQ_DATASET_SILVER`, `BQ_DATASET_GOLD` e `BQ_DATASET_OPS` passaram a
    ser lidos por `Settings`.
-   DDL versionado em `sql/bronze/tables.sql`,
    `sql/bronze/staging_tables.sql` e `sql/ops/ingestion_batches.sql` é a
    única fonte de verdade dos schemas. Datasets, bucket e IAM continuam
    sob responsabilidade do Terraform.
-   Carga implementada: GCS → tabela de staging com schema explícito,
    `WRITE_TRUNCATE` e `max_bad_records=0`; depois `MERGE` nas tabelas
    finais pelas chaves de negócio, com `batch_id`, `source_file`,
    `ingested_at` e `ingestion_date`.
-   Lote de `2026-11-17` carregado e conferido no BigQuery: `customers`
    (10 linhas), `contracts` (13) e `installments` (78). Todos os lotes
    estão `SUCCEEDED` em `ops.ingestion_batches`.
-   Reexecução do mesmo lote reconheceu o status `SUCCEEDED` e não criou
    duplicatas. Falha sintética em teste unitário marca o lote como
    `FAILED` sem registrar sucesso.
-   Testes: 24 passaram e 2 integrações opt-in ficaram disponíveis; a
    integração real contra o BigQuery passou.

**Parar e pedir aprovação.**

### Fase 6 --- Transformações dbt: Silver e Gold (concluída)

**Objetivo:** implementar ELT no BigQuery com dbt-core.

Decisões registradas nos ADRs 0002 e 0007.

Tarefas:

1.  Criar projeto dbt com `dbt_project.yml`, `profiles.yml` sem segredos
    e `sources.yml` apontando para a Bronze.
2.  Implementar modelos Silver com padronização de tipos, datas, códigos
    e valores.
3.  Definir deduplicação determinística e modelos incrementais com
    `merge`, `unique_key`, partição, cluster e janela para dados que
    chegam atrasados.
4.  Implementar modelos Gold a partir das perguntas de negócio, com
    contratos de modelo quando útil.
5.  Criar testes genéricos (`unique`, `not_null`, `relationships`,
    `accepted_values`) e testes singulares de datas e valores.
6.  Configurar `generate_schema_name` para separar `silver_dev`/`gold_dev`
    de `silver`/`gold`.
7.  Gerar `dbt docs` e validar lineage; executar `dbt build` de forma
    controlada.
8.  Não adicionar packages externos sem necessidade; manter SQL legível
    e versionado.
9.  Evitar transformações redundantes e dependências circulares.
10. Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (`dbt-core`/`dbt-bigquery` pinados,
    variáveis do dbt, `.gitignore`, testes e `docs/dev/setup.md`).

**Aceite:**

-   Modelos dbt legíveis, versionados e reproduzíveis.
-   Incrementalidade validada.
-   Duplicidades e registros inválidos tratados explicitamente.
-   Tabelas Gold respondem às perguntas analíticas definidas.
-   `dbt docs` e lineage gerados.
-   Consultas consideram custo e particionamento.

**Resultado da execução (2026-11-19):**

-   `dbt-core==1.12.6` e `dbt-bigquery==1.12.3` foram adicionados e fixados
    juntos no `pyproject.toml`/`uv.lock`. Nenhum dbt package externo foi
    adicionado.
-   O projeto dbt foi criado em `dbt/` com `dbt_project.yml`, `profiles.yml`
    sem segredos, `sources.yml` para as três tabelas da Bronze, macro
    `generate_schema_name`, modelos Silver/Gold, documentação de colunas e
    testes genéricos/singulares.
-   O Terraform passou a criar `silver_dev` e `gold_dev` e a conceder
    `roles/bigquery.dataEditor` na conta de serviço `lakehouse-dbt`.
    `apply` autorizado: `Apply complete! Resources: 4 added, 0 changed, 0
    destroyed.`
-   Modelos Silver usam `merge`, `unique_key`, partição por `updated_at`,
    clustering, janela de 3 dias para atraso e deduplicação
    determinística. Contratos são enforcement apenas na Silver, com
    `on_schema_change: fail`.
-   A data de referência analítica é `2026-01-31`.
    `mart_carteira_credito` considera contratos `active`/`closed` com
    cobertura no fim do mês; `mart_inadimplencia` considera parcelas
    vencidas e não pagas até a data de referência; `fato_pagamentos`
    consolida parcelas com `paid_at` preenchido.
-   `dbt parse`, `dbt compile`, `dbt build --full-refresh` e
    `dbt docs generate` passaram em `dev`. Resultado: `PASS=83 WARN=0
    ERROR=0 SKIP=0` (6 modelos e 77 testes).
-   Contagens conferidas: `silver_dev.silver_customers` 10,
    `silver_dev.silver_contracts` 13, `silver_dev.silver_installments` 78,
    `gold_dev.mart_carteira_credito` 38,
    `gold_dev.mart_inadimplencia` 13 e `gold_dev.fato_pagamentos` 61.
-   `store_failures`, `dbt source freshness` e `ops.dq_results` ficaram
    explicitamente adiados para a Fase 7.

**Parar e pedir aprovação.**

### Fase 7 --- Qualidade, idempotência e recuperação (concluída)

**Objetivo:** provar que o pipeline é confiável.

Decisões registradas no ADR 0008.

Tarefas:

1.  Criar testes dbt para campos obrigatórios, unicidade,
    relacionamentos e domínio.
2.  Criar testes singulares para valores e datas fora das regras.
3.  Configurar `store_failures` e `dbt source freshness`.
4.  Executar `dbt build` do mesmo lote mais de uma vez.
5.  Simular falha entre etapas e definir retomada segura.
6.  Verificar contagens de entrada, saída e rejeitados e persistir o
    resumo em `ops.dq_results`.
7.  Documentar limitações e regras para correção/reprocessamento.
8.  Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (testes de qualidade/idempotência e
    `docs/dev/setup.md`).

**Aceite:**

-   Reexecução não causa duplicidade.
-   Falhas podem ser diagnosticadas.
-   Registros inválidos são contabilizados.
-   Resultados de testes e freshness ficam rastreáveis por lote.
-   Testes cobrem os principais cenários positivos e negativos.

**Resultado da execução (2026-11-19):**

-   O Terraform passou a criar `bronze_dbt_test__audit` e a conceder
    `roles/bigquery.dataEditor` nele à conta de serviço `lakehouse-dbt`.
    `apply` autorizado: `Apply complete! Resources: 2 added, 0 changed, 0
    destroyed.`
-   `dbt_project.yml` configura `store_failures` com
    `+schema: bronze_dbt_test__audit`. A macro `generate_schema_name`
    mantém esse nome sem sufixo `_dev` para testes, evitando datasets de
    auditoria duplicados. As fontes Bronze usam
    `loaded_at_field: ingested_at` com `warn_after=72h` e
    `error_after=168h`.
-   `dbt build` foi reexecutado sem alterações nas contagens. A validação
    final registrou `PASS=83 WARN=0 ERROR=0` no build e `PASS=77` no
    `dbt test`; `dbt source freshness` retornou 3 fontes `PASS`, com
    maior idade de `45.5` horas.
-   Um teste temporário que forçou falha gravou corretamente em
    `bronze_dbt_test__audit`. Após removê-lo, o `dbt test` completo deixou
    77 tabelas de auditoria. O teste temporário e os datasets incorretos
    `bronze_dbt_test__audit_dev` e `dbt_test__audit_dev` foram removidos.
-   `sql/ops/dq_results.sql` cria a tabela de resumo particionada por
    `ingestion_date`. A primeira tentativa com `insert_rows_json` deixou
    buffer de streaming; a tabela de teste foi recriada a partir do DDL e
    a escrita final passou a usar `load_table_from_json` com decorador de
    partição e `WRITE_TRUNCATE`.
-   `uv run python -m lakehouse.quality --ingestion-date 2026-11-17` foi
    executado duas vezes: `12 linhas gravadas` nas duas, todas `PASS`.
    Contagens: clientes `10/10`, contratos `13/13`, parcelas `78/78`,
    `rejected_count=0`, `dbt_tests_passed=77`, `dbt_tests_failed=0` e
    freshness máxima `45.5h`.
-   A simulação com `as_of_date` inválido confirmou que a Silver termina e
    a Gold falha. A retomada com o valor correto restaurou o build sem
    limpeza manual nem duplicidade.
-   Nenhuma dependência Python nova foi adicionada; o módulo usa
    `google-cloud-bigquery` e stdlib. O procedimento está em
    `docs/runbook.md`.

**Parar e pedir aprovação.**

### Fase 8 --- CI/CD e DevSecOps

**Objetivo:** automatizar verificações e implantação controlada.

Orquestração registrada no ADR 0003; segurança mínima no ADR 0004.

Tarefas:

1.  Criar workflow de CI para pull requests.
2.  Executar testes Python.
3.  Executar `dbt deps` (quando houver packages), `dbt parse`,
    `dbt compile` e `sqlfluff lint`.
4.  Executar `dbt build` e `dbt docs generate` de forma controlada em
    dataset de teste, preferencialmente em execução manual ou na branch
    principal.
5.  Publicar artefatos do dbt (`manifest.json`, `run_results.json`,
    `catalog.json` e docs) para diagnóstico.
6.  Executar `terraform fmt` e `terraform validate`.
7.  Executar Gitleaks.
8.  Executar Checkov nos arquivos Terraform.
9.  Configurar autenticação GitHub → GCP via Workload Identity
    Federation.
10. Separar validação de `plan` da aplicação de mudanças.
11. Exigir aprovação humana antes de implantação em recursos de
    produção/demonstração.
12. Restringir permissões do workflow e proteger secrets/variables.
13. Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (`sqlfluff`, Gitleaks/Checkov,
    `.gitignore`, testes e `docs/dev/setup.md`).

**Aceite:**

-   Pull request executa as verificações.
-   `dbt parse`, `dbt compile` e `sqlfluff` passam no CI.
-   `dbt build` controlado funciona e publica artefatos.
-   Falhas críticas bloqueiam o fluxo.
-   Nenhuma chave de service account é armazenada no GitHub.
-   `apply` não ocorre automaticamente sem a política de aprovação
    definida.
-   Logs do workflow permitem entender falhas.

**Parar e pedir aprovação.**

### Fase 9 --- Observabilidade e operação

**Objetivo:** permitir acompanhar e diagnosticar execuções com o menor
custo operacional possível.

Tarefas:

1.  Padronizar logs estruturados no Python.
2.  Enviar os logs estruturados ao Cloud Logging, sem incluir credenciais
    ou dados sensíveis; manter baixo volume e retenção padrão.
3.  Aproveitar logs e métricas nativas de jobs do BigQuery e do dbt.
4.  Coletar `run_results.json` e `manifest.json` do dbt para registrar
    duração, status e contagens de linhas; criar métricas customizadas
    somente se forem necessárias para a demonstração e com baixa
    cardinalidade.
5.  Configurar no Cloud Monitoring um alerta operacional simples para
    falha do pipeline, preferindo uma condição baseada em logs.
6.  Criar procedimento de diagnóstico e reprocessamento.
7.  Evitar métricas, painéis ou alertas sem uso definido.
8.  Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (cliente de logging se necessário,
    `LOG_LEVEL`, testes e `docs/dev/setup.md`).

**Importante:**
 scripts executados localmente ou no GitHub Actions não
aparecem automaticamente no Cloud Logging. Implementar e validar o envio
explícito de logs para demonstrar logging centralizado. Conferir o volume
de ingestão e a retenção para manter o uso dentro dos níveis gratuitos
atuais sempre que possível; excedentes podem ser cobrados.

**Aceite:**

-   Uma execução pode ser rastreada por `batch_id`.
-   Falhas relevantes podem ser encontradas.
-   Alertas testados.
-   Runbook documentado.

**Parar e pedir aprovação.**

### Fase 10 --- Documentação, demonstração e encerramento

**Objetivo:** transformar a implementação em um projeto apresentável e
reproduzível.

Tarefas:

1.  Mover esta especificação para `docs/spec.md` e criar um README
    público com problema, arquitetura real, demonstração, custos,
    trade-offs e roadmap.
2.  Criar diagrama final.
3.  Documentar decisões técnicas e trade-offs, incluindo a adoção do
    dbt e a orquestração via GitHub Actions.
4.  Documentar setup, execução, testes, deploy e limpeza.
5.  Publicar ou anexar o `dbt docs` e o diagrama de lineage.
6.  Criar exemplo de execução bem-sucedida e de falha recuperável.
7.  Registrar métricas demonstráveis: volume, duração, rejeições e custo
    estimado, sem inventar resultados.
8.  Preparar roteiro de demonstração para palestra.
9.  Criar seção de limitações e próximos passos.
10. Atualizar os artefatos da Fase 1 conforme
    `docs/dev/fase1-evolucao.md` (README público, `docs/spec.md` e
    `docs/dev/setup.md` final).

**Aceite:**

-   Uma pessoa consegue entender o projeto e reproduzir o fluxo seguindo
    a documentação.
-   O diagrama corresponde ao que está implantado.
-   A demonstração evidencia Engenharia de Dados, DataOps e DevSecOps.
-   Custos e limitações estão descritos.

------------------------------------------------------------------------

## 8. Regras para a LLM que implementará o projeto

Estas regras são obrigatórias durante toda a interação.

### 8.1 Trabalhar em etapas pequenas

-   Leia este README antes de propor alterações.
-   Identifique a fase atual e o que já está implementado.
-   Trabalhe somente na fase autorizada.
-   Divida a fase em tarefas pequenas e explique o objetivo de cada uma.
-   Não gere o projeto inteiro de uma vez.
-   Não avance automaticamente para a próxima fase.
-   Ao final, pare e aguarde a avaliação do usuário.

### 8.2 Explicar antes de alterar

Antes de criar ou modificar arquivos:

1.  Explique o que pretende fazer.
2.  Informe quais arquivos serão criados ou alterados.
3.  Explique a decisão técnica e as alternativas relevantes.
4.  Aponte impactos de custo, segurança e manutenção.
5.  Aguarde confirmação quando a alteração envolver infraestrutura,
    permissões, custos ou mudança de arquitetura.

Para alterações locais pequenas e reversíveis dentro da fase aprovada,
pode implementar após explicar o plano.

### 8.3 Preservar o aprendizado do usuário

-   Não esconder decisões em abstrações ou código excessivamente
    complexo.
-   Preferir funções pequenas, nomes claros e responsabilidades únicas.
-   Explicar conceitos novos no contexto em que aparecem.
-   Não despejar grandes blocos de código sem explicar como se encaixam.
-   Apresentar comandos de execução e como verificar seus resultados.
-   Quando houver mais de uma alternativa válida, recomendar uma e
    justificar brevemente.

### 8.4 Segurança e operações

-   Nunca solicitar, imprimir ou registrar credenciais.
-   Nunca adicionar arquivos `.env`, chaves JSON, tokens ou state local
    ao Git.
-   Não executar comandos destrutivos sem autorização.
-   Não executar `terraform apply`, `terraform destroy`, exclusões de
    buckets/datasets ou alterações de IAM sem confirmação explícita.
-   Antes de comandos que possam gerar cobrança, explicar o recurso, o
    custo potencial e como removê-lo.
-   Não presumir que um alerta de orçamento impede gastos.
-   Não usar dados financeiros reais.
-   Não ampliar permissões para resolver erros sem primeiro investigar a
    permissão mínima necessária.

### 8.5 Qualidade das alterações

-   Criar testes junto com a funcionalidade.
-   Executar testes e validações após cada mudança relevante.
-   Não ignorar erros ou desabilitar verificações apenas para fazer o
    pipeline passar.
-   Não adicionar dependências sem justificar sua necessidade.
-   Não duplicar configuração em vários arquivos.
-   Manter documentação alinhada ao código.
-   Não declarar uma etapa concluída sem apresentar evidência de teste.

### 8.6 Formato obrigatório de encerramento de cada etapa

Ao concluir uma etapa, responder com:

1.  **Objetivo da etapa**
2.  **O que foi implementado**
3.  **Arquivos criados ou alterados**
4.  **Decisões técnicas e justificativas**
5.  **Comandos executados**
6.  **Testes realizados e resultados**
7.  **Pendências, limitações e riscos**
8.  **Próxima etapa sugerida**

Finalizar perguntando se o usuário aprova o resultado e autoriza a
próxima etapa.

------------------------------------------------------------------------

## 9. Critérios gerais de sucesso

O projeto será considerado bem-sucedido quando:

-   O fluxo batch ELT funcionar de ponta a ponta.
-   Os dados estiverem organizados nas camadas Medallion.
-   Lineage, testes e documentação do dbt estiverem disponíveis.
-   Cargas incrementais e reexecuções forem seguras.
-   Qualidade dos dados for testada e mensurada.
-   A infraestrutura puder ser reproduzida por Terraform.
-   CI executar testes e verificações de segurança.
-   Credenciais e permissões seguirem boas práticas.
-   Logs e alertas permitirem diagnosticar problemas.
-   A documentação refletir fielmente a implementação.
-   A arquitetura puder ser explicada em uma palestra sem depender de
    componentes que não agregam ao objetivo.

## 10. Mensagem inicial para a LLM

Ao iniciar o trabalho, a LLM deve:

1.  Ler este README integralmente.
2.  Inspecionar o repositório e os ADRs em `docs/decisions/` para
    identificar o que já existe e quais decisões estão aceitas.
3.  Não sobrescrever nem recriar arquivos sem verificar seu conteúdo.
4.  Informar a fase atual e apresentar um plano curto para ela.
5.  Começar pela **Fase 0 --- Alinhamento e desenho**.
6.  Não escrever código nem provisionar recursos antes da aprovação do
    desenho.
7.  Aguardar a confirmação do usuário antes de avançar.

**Regra final:** o objetivo não é terminar rapidamente nem utilizar o
maior número possível de tecnologias. O objetivo é construir,
compreender, testar e explicar uma arquitetura de Engenharia de Dados
simples, escalável e segura, uma etapa por vez.
