# ADR 0005 — State local do Terraform no MVP

- **Status:** aceita e aplicada na Fase 3
- **Data:** 2026-11-17

## Contexto

O Terraform precisará guardar state para os recursos mínimos do MVP: um
bucket GCS, quatro datasets BigQuery, APIs e IAM. O projeto é manual,
executado por uma pessoa, e o README pede custo mínimo e ausência de
serviços opcionais.

## Decisão

Manter o state local em `infrastructure/terraform/terraform.tfstate`,
ignorado pelo Git, e versionar `.terraform.lock.hcl` para fixar a versão
do provider. Não criar bucket remoto de state nesta fase.

## Alternativas consideradas

- **Bucket GCS remoto:** permitiria colaboração e execução via CI, mas
  exigiria bootstrap controlado, permissões restritas, um bucket
  adicional e atenção ao risco de dependência circular entre backend e
  recursos gerenciados. O custo é pequeno, mas não é necessário agora.
- **State em repositório:** rejeitado por conter identificadores de
  recursos e por criar risco de sobrescrita e exposição.

## Consequências

- `terraform plan`, `apply` e `destroy` devem ser executados no mesmo
  diretório que contém o state.
- Não há colaboração simultânea nem execução remota segura de Terraform
  enquanto o state for local.
- `.terraform/`, `*.tfstate` e `*.tfvars` ficam fora do Git;
  `terraform.tfvars.example` e `.terraform.lock.hcl` são versionados.
- Se a Fase 8 adotar GitHub Actions com WIF, o backend remoto será
  reavaliado antes de configurar o deploy, com plano de custo e
  bootstrap explícitos.
