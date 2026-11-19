# ADR 0004 — Segurança automatizada mínima

- **Status:** aceita
- **Data:** 2026-11-08

## Contexto

O objetivo é demonstrar DevSecOps sem transformar o portfólio em uma
coleção de scanners. O conjunto mínimo escolhido é Gitleaks para segredos
e Checkov para Terraform. O projeto usa dados sintéticos, execução
manual e nenhum dado real.

## Decisão

Manter no MVP apenas Gitleaks e Checkov como verificações automatizadas
de segurança. Não adicionar Bandit, pip-audit, Trivy, CodeQL, SBOM ou
workflows de Dependabot nesta versão.

## Controles compensatórios

- Autenticação sem chave: ADC local e WIF/OIDC no GitHub Actions.
- Proibição de chave JSON de service account no repositório.
- Org policy `iam.disableServiceAccountKeyCreation` no projeto.
- IAM de menor privilégio, com identidades separadas para deploy e
  execução do pipeline.
- Dependências mínimas e pinadas em lockfile.
- Revisão obrigatória de pull requests e branch protection.
- Gitleaks no pre-commit e no CI.
- Checkov no CI para o Terraform.
- Nenhum dado real, credencial ou segredo em logs e artefatos.

## Exceções do Checkov

Algumas verificações são inaplicáveis ao MVP sintético e foram desativadas
em `.checkov.yml`, com justificativa registrada aqui:

- `CKV_GCP_62` e `CKV_GCP_78`: o bucket de landing não usa logs de acesso
  nem versionamento. Os dados são sintéticos, o upload usa
  `if_generation_match=0` e o ciclo de vida remove objetos após 30 dias,
  evitando custo adicional.
- `CKV_GCP_81`: não há CSEK. O projeto usa criptografia gerenciada pelo
  Google por padrão, sem gerenciar chaves próprias nesta demonstração.
- `CKV_GCP_41` e `CKV_GCP_49`: a SA de CI precisa de papéis no nível do
  projeto para criar e administrar SAs e IAM via Terraform. O risco é
  mitigado por WIF sem chaves, org policy que proíbe chaves de SA,
  identidades separadas e aprovação humana para `apply`.
- `CKV_GCP_125`: a regra exige uma condição literal sobre `assertion.sub`,
  o que impediria o mesmo provider de atender push em `main` e pull
  requests. A condição adotada restringe `attribute.repository` ao
  repositório do projeto, os claims mapeados são apenas `sub`, `actor` e
  `repository`, e o audience é limitado ao próprio provider.

## Riscos aceitos

- Vulnerabilidades em dependências Python não são detectadas
  automaticamente.
- Não há SAST específico para código Python.
- Não há varredura de imagem de container, SBOM ou assinatura de
  artefatos.
- A detecção depende de revisão manual e de manter dependências poucas e
  atualizadas.

## Critérios de reversão

Reavaliar a decisão se o projeto passar a usar dados reais, ganhar
dependências relevantes, publicar imagem de container, receber
contribuições externas ou se uma vulnerabilidade exigir resposta mais
rápida. Nesses casos, adicionar primeiro `pip-audit` e Dependabot, que
têm menor custo de adoção.

## Consequências

- O conjunto de segurança fica pequeno, compreensível e barato.
- O portfólio perde amplitude em supply chain e SAST, o que deve ser
  explicitado na documentação pública.
- Os controles de identidade e permissão continuam sendo a parte mais
  forte da demonstração de DevSecOps.
