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
