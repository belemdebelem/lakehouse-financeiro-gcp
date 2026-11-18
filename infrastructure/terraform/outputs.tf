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
