locals {
  datasets = toset(["bronze", "bronze_dbt_test__audit", "silver", "silver_dev", "gold", "gold_dev", "ops"])
}

resource "google_project_service" "serviceusage" {
  project            = var.project_id
  service            = "serviceusage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "required" {
  for_each = toset([
    "bigquery.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [google_project_service.serviceusage]
}

resource "google_storage_bucket" "landing" {
  name                        = var.bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = var.labels

  depends_on = [google_project_service.required]
}

resource "google_bigquery_dataset" "layers" {
  for_each = local.datasets

  dataset_id                 = each.value
  project                    = var.project_id
  location                   = var.region
  delete_contents_on_destroy = true
  description                = "Camada ${each.value} do lakehouse financeiro sintético."
  labels                     = var.labels

  depends_on = [google_project_service.required]
}

resource "google_service_account" "pipeline" {
  account_id   = "lakehouse-pipeline"
  display_name = "Execucao do pipeline de ingestao e carga"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_service_account" "dbt" {
  account_id   = "lakehouse-dbt"
  display_name = "Execucao das transformacoes dbt"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "pipeline_object_creator" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_object_viewer" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "pipeline_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "dbt_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_project_iam_member" "pipeline_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "dbt_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_monitoring_notification_channel" "alert_email" {
  count        = var.alert_email == "" ? 0 : 1
  project      = var.project_id
  display_name = "Lakehouse financeiro: email de alertas"
  description  = "Notificações de falha do pipeline financeiro."
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "pipeline_failure" {
  project      = var.project_id
  display_name = "Lakehouse financeiro: falha de pipeline"
  combiner     = "OR"
  enabled      = true
  notification_channels = var.alert_email == "" ? [] : [
    google_monitoring_notification_channel.alert_email[0].name
  ]

  conditions {
    display_name = "Evento de falha emitido pelo pipeline"

    condition_matched_log {
      filter = <<-EOT
        resource.type="global"
        logName="projects/${var.project_id}/logs/lakehouse-financeiro-pipeline"
        jsonPayload.pipeline_name="lakehouse-financeiro"
        jsonPayload.status="failure"
      EOT
    }
  }

  alert_strategy {
    auto_close = "604800s"

    notification_rate_limit {
      period = "300s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Falha do lakehouse financeiro. Consulte Cloud Logging e use batch_id/invocation_id para rastrear a execução."
  }

  user_labels = var.labels

  depends_on = [google_project_service.required]
}

resource "google_bigquery_dataset_iam_member" "pipeline_bronze_editor" {
  dataset_id = google_bigquery_dataset.layers["bronze"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "pipeline_ops_editor" {
  dataset_id = google_bigquery_dataset.layers["ops"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_bronze_viewer" {
  dataset_id = google_bigquery_dataset.layers["bronze"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_audit_editor" {
  dataset_id = google_bigquery_dataset.layers["bronze_dbt_test__audit"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_silver_editor" {
  dataset_id = google_bigquery_dataset.layers["silver"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_gold_editor" {
  dataset_id = google_bigquery_dataset.layers["gold"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_silver_dev_editor" {
  dataset_id = google_bigquery_dataset.layers["silver_dev"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_gold_dev_editor" {
  dataset_id = google_bigquery_dataset.layers["gold_dev"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_bigquery_dataset_iam_member" "dbt_ops_editor" {
  dataset_id = google_bigquery_dataset.layers["ops"].dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dbt.email}"
}
