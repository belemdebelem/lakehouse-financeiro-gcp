# Terraform do MVP (Fases 3 e 6)

## Recursos versionados

- APIs: `serviceusage`, `cloudresourcemanager`, `iam`, `storage` e
  `bigquery`, apenas as necessárias aos recursos aprovados.
- GCS: um bucket regional Standard para Landing/Raw, com acesso uniforme,
  prevenção de acesso público, versionamento desligado e retenção de 30
  dias para dados de demonstração.
- BigQuery: datasets `bronze`, `silver`, `silver_dev`, `gold`, `gold_dev` e
  `ops` na mesma região do bucket. Os datasets `*_dev` isolam as execuções
  locais do dbt na Fase 6.
- IAM: duas contas de serviço separadas — `lakehouse-pipeline` e
  `lakehouse-dbt`.
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

O state é local (`terraform.tfstate`) e ignorado pelo Git. Isso evita um
bucket adicional e seu custo, mas impede colaboração e execução remota
segura. O `.terraform.lock.hcl` é versionado para fixar o provider.
A mudança para backend remoto será avaliada na Fase 8, quando houver
GitHub Actions; veja `docs/decisions/0005-estado-local-terraform.md`.

## IAM

| Identidade | Permissões concedidas |
|---|---|
| `lakehouse-pipeline` | `storage.objectCreator` e `storage.objectViewer` no bucket; `bigquery.jobUser` no projeto; `bigquery.dataEditor` em `bronze` e `ops`. |
| `lakehouse-dbt` | `bigquery.jobUser` no projeto; `bigquery.dataViewer` em `bronze`; `bigquery.dataEditor` em `silver`, `silver_dev`, `gold`, `gold_dev` e `ops`. |
| Usuário local via ADC | Permissões administrativas necessárias para `plan`/`apply`, fora do Terraform e fora do repositório. |
| CI/deploy (Fase 8) | Identidade separada via Workload Identity Federation; papéis mínimos serão definidos quando o CD existir. |

As permissões de leitura no bucket são necessárias para a precondição de
geração usada na ingestão (Fase 4), que evita sobrescrever o original.

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
