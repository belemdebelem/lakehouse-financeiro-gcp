# Terraform do MVP (Fases 3, 6, 7 e 8)

## Recursos versionados

- APIs: `serviceusage`, `cloudresourcemanager`, `iam`, `iamcredentials`,
  `sts`, `storage` e `bigquery`, apenas as necessárias aos recursos
  aprovados.
- GCS: um bucket regional Standard para Landing/Raw, com acesso uniforme,
  prevenção de acesso público, versionamento desligado e retenção de 30
  dias para dados de demonstração.
- BigQuery: datasets `bronze`, `bronze_dbt_test__audit`, `silver`,
  `silver_dev`, `gold`, `gold_dev` e `ops` na mesma região do bucket. Os
  datasets `*_dev` isolam as execuções locais do dbt na Fase 6; o dataset de
  auditoria guarda falhas dos testes na Fase 7.
- IAM: três contas de serviço separadas — `lakehouse-pipeline`,
  `lakehouse-dbt` e `lakehouse-ci`.
- Observabilidade: APIs de Cloud Logging/Monitoring, papel
  `roles/logging.logWriter` para as contas do pipeline e dbt e uma política
  de alerta baseada em eventos JSON com `status=failure`.
- WIF/OIDC: pool `github-actions`, provider `github` e vínculo restrito ao
  repositório `belemdebelem/lakehouse-financeiro-gcp`.
- Nenhum Cloud Scheduler, Composer, Dataflow, bucket de state ou serviço
  opcional é criado nesta fase.

## Pré-requisitos

- Terraform >= 1.7.
- Application Default Credentials (ADC): `gcloud auth application-default
  login`. Não usar chaves JSON de service account.
- Projeto GCP com faturamento ativo e permissão para habilitar APIs,
  criar bucket/datasets e conceder IAM.

## Uso

```bash
cd infrastructure/terraform
terraform init
terraform fmt -check -recursive
terraform validate
cp terraform.tfvars.example terraform.tfvars
terraform plan
```

`terraform apply` e `terraform destroy` exigem aprovação explícita e não
são executados automaticamente. O `terraform.tfvars` preenchido fica fora
do Git; o repositório versiona apenas `terraform.tfvars.example`.

## State

O state Terraform foi migrado para o backend GCS no bucket do lakehouse,
com prefixo `terraform/state/lakehouse-financeiro`; nenhum bucket adicional
foi criado. O workflow de CD gera `backend.tf` e `backend.hcl` para usar
esse backend. Para operações locais, inicialize o backend GCS antes de
executar comandos Terraform. O `.terraform.lock.hcl` é versionado para
fixar o provider. Veja `docs/decisions/0009-ci-cd-wif-scanners-state.md`.

## IAM

| Identidade | Permissões concedidas |
|---|---|
| `lakehouse-pipeline` | `storage.objectCreator` e `storage.objectViewer` no bucket; `bigquery.jobUser` no projeto; `bigquery.dataEditor` em `bronze` e `ops`; `logging.logWriter` no projeto. |
| `lakehouse-dbt` | `bigquery.jobUser` no projeto; `bigquery.dataViewer` em `bronze`; `bigquery.dataEditor` em `bronze_dbt_test__audit`, `silver`, `silver_dev`, `gold`, `gold_dev` e `ops`; `logging.logWriter` no projeto. |
| `lakehouse-ci` | `serviceusage.serviceUsageAdmin`, `storage.admin`, `bigquery.admin`, `iam.serviceAccountAdmin`, `iam.workloadIdentityPoolAdmin`, `iam.serviceAccountUser` e `resourcemanager.projectIamAdmin` no projeto, para `plan`/`apply` controlado. |
| Principal WIF do repositório | `iam.workloadIdentityUser` nas três contas de serviço; restrito ao repositório e sem chaves JSON. |
| Usuário local via ADC | Permissões administrativas necessárias para `plan`/`apply`, fora do Terraform e fora do repositório. |

As permissões de leitura no bucket são necessárias para a precondição de
geração usada na ingestão (Fase 4), que evita sobrescrever o original.

## CI/CD (Fase 8)

O workflow `CD - Terraform` executa `plan` e `apply` em jobs separados; o
`apply` exige o environment `demo` com revisores configurados no GitHub.
As variáveis `GCP_PROJECT_ID`, `GCS_BUCKET_NAME`, `GCP_WIF_PROVIDER` e
`GCP_CI_SA` estão configuradas no repositório. O `apply` inicial criou 15
recursos; o state foi migrado para o backend GCS e o `plan` posterior do CD
terminou sem mudanças. Os revisores do environment `demo` também estão
configurados.

## Orçamento e alertas

O orçamento não é criado por Terraform porque depende da conta de
faturamento e de permissões de billing. Na conta de billing deste projeto
já existe o orçamento mensal `R$ 1 Alerta de orçamento mensal`, sem filtro
de projeto (cobre este projeto e os demais da conta), com limiares de 50%,
90%, 100% e 150% do gasto real e notificações aos destinatários padrão de IAM
da conta de billing. Ele foi reutilizado; nenhum orçamento duplicado foi
criado.

Registre que o alerta **não bloqueia** cobranças. Não versione o ID da
conta de billing nem dados de faturamento. Se o orçamento atual for
alterado ou removido, recrie-o no Console com escopo no projeto e limiares
de 50%, 90% e 100%.

Confirme os níveis gratuitos e preços atuais antes da implantação. A
região `southamerica-east1` não recebe a franquia gratuita do GCS; a
estimativa e o trade-off estão no ADR 0001.

## Limpeza e custo

- `force_destroy = true` no bucket e `delete_contents_on_destroy = true`
  nos datasets permitem remover os dados de demonstração com
  `terraform destroy`, somente após aprovação.
- A regra de ciclo de vida apaga objetos com mais de 30 dias no bucket.
- Execute o pipeline manualmente e confira o Billing Reports após cada
  sessão de uso. O alerta de orçamento é apenas aviso.
- Logs enviados pelo pipeline usam o Cloud Logging. A franquia e o preço
  aplicáveis dependem do volume mensal e da conta; verifique os preços
  vigentes e acompanhe o volume. A demonstração emite poucos registros por
  execução. Configure o canal de alerta usando `TF_VAR_alert_email`; o valor
  não deve ser versionado. Um único canal de e-mail está associado à política
  de falha para conter custos.
- Uma política log-based tem custo estimado em cerca de US$ 0,035/mês nos
  preços atuais; a franquia de 50 GiB/mês de Logging é compartilhada por
  todo o projeto. Consulte os links de preço no runbook antes de aumentar o
  volume de logs ou adicionar políticas.
