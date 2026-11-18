# ADR 0001 — Arquitetura MVP, segurança e custo

- **Status:** aceita para o MVP (região a confirmar antes da Fase 3)
- **Data:** 2026-11-08

## Contexto

O projeto precisa demonstrar engenharia de dados em GCP e práticas de
DevSecOps para portfólio, com dados sintéticos, batch e custo mínimo.
O projeto GCP já está associado a faturamento. A demonstração também
deve preservar logging e monitoramento reais, sem fingir resultados ou
desativar controles de segurança.

## Decisões

1. Usar GCS para Landing/Raw e BigQuery para Bronze, Silver, Gold e uma
   tabela operacional simples. Python executa ingestão e cargas batch na
   Bronze; dbt-core executa as transformações ELT de Silver e Gold.
2. Usar `southamerica-east1` para bucket e datasets como padrão inicial,
   evitando transferências entre regiões e mantendo a localização perto
   do usuário. Confirmar a escolha antes de criar recursos; a franquia
   gratuita do GCS está restrita a algumas regiões dos EUA.
3. Executar manualmente e usar dados sintéticos pequenos. Não criar
   recursos de computação contínuos, streaming, agendamento, reservas de
   slots ou serviços fora do escopo.
4. Configurar orçamento mensal de valor baixo (referência: US$ 1) com
   alertas de gasto. O orçamento é aviso e não é limite rígido de uso.
5. Manter segurança demonstrável com IAM de menor privilégio, ADC local,
   Workload Identity Federation no GitHub Actions, Gitleaks e Checkov.
   Usar Secret Manager para segredos reais se forem necessários; não
   inventar segredo só para preencher o serviço.
6. Enviar logs estruturados ao Cloud Logging e configurar um alerta
   simples de falha no Cloud Monitoring. Usar métricas nativas e evitar
   métricas customizadas de alta cardinalidade, dashboards grandes e
   uptime checks.
7. Manter arquivos Landing/Raw em GCS Standard regional com limpeza
   curta dos dados da demonstração; desligar versionamento e evitar
   sobrescrita por precondição de geração. Avaliar state remoto do
   Terraform separadamente e apresentar seu custo/bootstrapping no plano.
8. Usar CSV UTF-8 determinístico com clientes, contratos e parcelas;
   pagamentos parciais e dados reais ficam fora do MVP.
9. Modelar carteira como principal original de contratos ativos, deixando
   explícito que não é saldo amortizado. Modelar inadimplência e pagamentos
   a partir das parcelas e suas datas/valores.
10. Usar dbt-core + dbt-bigquery apenas para Silver e Gold, com testes,
    contratos, incrementalidade e docs. O GitHub Actions orquestra a
    sequência ingestão → Bronze → `dbt build`; dbt Cloud e recursos pagos
    ficam fora. Detalhes nos ADRs 0002 e 0003.
11. Manter a segurança automatizada em Gitleaks e Checkov, com controles
    compensatórios e riscos aceitos registrados no ADR 0004.

## Estimativa de custo

Estimativa de planejamento: aproximadamente **US$ 0,01–0,10 por mês**
com até 1 GiB em GCS em São Paulo, poucos uploads/cargas, consultas bem
abaixo de 1 TiB/mês e poucos logs. A maior parcela esperada é o
armazenamento do GCS. BigQuery oferece franquia mensal de 10 GiB de
armazenamento e 1 TiB de consultas; Cloud Logging tem franquia de 50
GiB por projeto/mês e retenção padrão de 30 dias. As franquias podem ser
consumidas por outros projetos/uso da mesma conta e os preços podem
mudar. Excedentes, tráfego entre regiões, egress, retenção adicional e
recursos não descritos podem elevar o valor. Consultar Billing após
cada demonstração.

## Consequências

- O desenho demonstra as tecnologias centrais sem exigir serviços
  sempre ligados.
- dbt não é orquestrador; a sequência é controlada pelo pipeline Python
  e pelo GitHub Actions. O custo do dbt é o tempo de CI e os bytes
  processados no BigQuery; não há licença.
- A segurança automatizada fica restrita a Gitleaks e Checkov, com os
  riscos e controles compensatórios registrados no ADR 0004.
- `southamerica-east1` não recebe a franquia gratuita do GCS; escolher
  uma região dos EUA pode reduzir armazenamento até os limites gratuitos,
  mas muda a localização dos dados. O usuário deve confirmar essa troca
  antes da Fase 3.
- O sandbox do BigQuery não serve para toda a demonstração porque não
  suporta DML como `MERGE`; usar o projeto faturado em modelo on-demand,
  com limites de bytes processados e volumes pequenos.
- O orçamento de faturamento alerta, mas não bloqueia cobrança. A
  estimativa não é garantia de valor máximo.
- Os serviços de Logging/Monitoring permanecem no escopo. A franquia
  gratuita reduz o custo esperado, mas não isenta excedentes.

## Fontes oficiais consultadas

- [Preços do Cloud Storage e regiões elegíveis à franquia gratuita](https://cloud.google.com/storage/pricing)
- [Preços do BigQuery](https://cloud.google.com/bigquery/pricing)
- [Preços de Cloud Logging e Cloud Monitoring](https://cloud.google.com/products/observability/pricing)
- [Orçamentos e alertas do Cloud Billing](https://cloud.google.com/billing/docs/how-to/budgets)
- [Limites do BigQuery sandbox](https://cloud.google.com/bigquery/docs/sandbox)
