data "google_project" "project" {
  project_id = var.project_id
}

locals {
  wif_pool_id     = "github-actions"
  wif_provider_id = "github"
  wif_audience    = "https://iam.googleapis.com/projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${local.wif_pool_id}/providers/${local.wif_provider_id}"
  wif_principal   = "principalSet://iam.googleapis.com/projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${local.wif_pool_id}/attribute.repository/${var.github_repository}"
  ci_project_roles = toset([
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/bigquery.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/iam.serviceAccountUser",
    "roles/resourcemanager.projectIamAdmin",
  ])
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = local.wif_pool_id
  display_name              = "GitHub Actions"
  description               = "Identidade federada para o repositorio ${var.github_repository}."

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = local.wif_provider_id
  display_name                       = "GitHub OIDC"
  description                        = "Provider OIDC dos workflows do GitHub Actions."
  attribute_condition                = "assertion.sub == \"repo:${var.github_repository}:ref:refs/heads/main\" || assertion.sub == \"repo:${var.github_repository}:pull_request\""

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri        = "https://token.actions.githubusercontent.com"
    allowed_audiences = [local.wif_audience]
  }

  depends_on = [google_iam_workload_identity_pool.github]
}

resource "google_service_account" "ci" {
  account_id   = "lakehouse-ci"
  display_name = "Execucao dos workflows de CI e CD"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_service_account_iam_member" "wif_ci" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.wif_principal
}

resource "google_service_account_iam_member" "wif_pipeline" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.wif_principal
}

resource "google_service_account_iam_member" "wif_dbt" {
  service_account_id = google_service_account.dbt.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.wif_principal
}

resource "google_project_iam_member" "ci" {
  for_each = local.ci_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.ci.email}"
}
