# ADR 0009 — CI/CD com WIF, scanners e backend GCS

- **Status:** aceita e aplicada na Fase 8
- **Data:** 2026-11-19

## Contexto

A Fase 8 precisa executar verificações em pull requests e permitir
implantação e build dbt sem chaves de service account. O projeto já usa
ADC local, GitHub Actions como orquestrador (ADR 0003) e segurança mínima
com Gitleaks e Checkov (ADR 0004). O state local da Fase 3 (ADR 0005) não
suporta execução remota segura do Terraform.

## Decisão

Adotar GitHub Actions com Workload Identity Federation/OIDC. O provider
aceita o audience padrão usado por `google-github-actions/auth`, derivado do
próprio nome do provider, e restringe o principal pelo repositório. Três
contas de serviço recebem o papel `iam.workloadIdentityUser` para esse
principal:

- `lakehouse-ci`: identidade de `plan`/`apply` do Terraform.
- `lakehouse-pipeline`: ingestão e carga Bronze no build controlado.
- `lakehouse-dbt`: `dbt compile`, `dbt build`, docs e resumo de qualidade.

O CI roda testes, Ruff, SQLFluff, `dbt parse`, Terraform `fmt`/`validate`,
Gitleaks e Checkov sem credenciais GCP. `dbt compile` usa WIF somente em
push na branch principal e em PRs do próprio repositório; forks ficam sem
acesso a variáveis e executam apenas as verificações locais.

O CD separa `plan` de `apply`. O `apply` e o build dbt usam o environment
`demo`, que deve ter revisores configurados no GitHub. Não há segredos de
GCP no repositório; configurações são variáveis do repositório.

O CD gera o backend GCS do Terraform, que reaproveita o bucket do lakehouse
com o prefixo `terraform/state/lakehouse-financeiro`. Nenhum bucket
adicional é criado. O state local foi migrado para esse backend; o `plan`
posterior executado pelo CD terminou sem mudanças.

## Alternativas consideradas

- **Chave JSON de service account:** rejeitada; a org policy já bloqueia a
  criação e o ADR 0004 exige ausência de chaves duradouras.
- **Permissões amplas para uma única SA:** rejeitada; separar CI, pipeline
  e dbt mantém o menor privilégio e facilita a auditoria.
- **Manter state local no CD:** rejeitado; plan e apply em runners
  efêmeros não teriam state compartilhado.
- **Criar bucket novo apenas para state:** rejeitado por ora; o bucket
  existente com prefixo dedicado evita custo e bootstrap adicionais.
- **Adicionar mais scanners ou Dependabot:** rejeitado pelo ADR 0004; o
  conjunto permanece Gitleaks, Checkov e SQLFluff.

## Consequências

- As variáveis `GCP_PROJECT_ID`, `GCP_REGION`, `GCS_BUCKET_NAME`,
  `BQ_DATASET_*`, `GCP_WIF_PROVIDER`, `GCP_CI_SA`, `GCP_PIPELINE_SA` e
  `GCP_DBT_SA` foram configuradas no GitHub.
- O environment `demo` tem revisor obrigatório configurado; a aprovação
  humana foi exercitada no build dbt controlado.
- O `apply` inicial foi executado localmente com ADC e criou 15 recursos.
  O state foi migrado para o bucket do lakehouse e o `plan` posterior do
  CD terminou sem mudanças.
- O bucket de state é gerenciado pelo próprio Terraform; isso é aceitável
  para a demonstração, mas exige cuidado em futura destruição do bucket.
