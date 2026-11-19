output "bucket_name" {
  description = "Nome do bucket Landing/Raw."
  value       = google_storage_bucket.landing.name
}

output "dataset_ids" {
  description = "Datasets BigQuery criados para as camadas."
  value       = [for dataset in google_bigquery_dataset.layers : dataset.dataset_id]
}

output "pipeline_service_account_email" {
  description = "Identidade de execução do pipeline."
  value       = google_service_account.pipeline.email
}

output "dbt_service_account_email" {
  description = "Identidade de execução do dbt."
  value       = google_service_account.dbt.email
}

output "ci_service_account_email" {
  description = "Identidade de execução dos workflows de CI e CD."
  value       = google_service_account.ci.email
}

output "wif_provider" {
  description = "Nome completo do provider WIF para uso na action google-github-actions/auth."
  value       = "projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${local.wif_pool_id}/providers/${local.wif_provider_id}"
}
