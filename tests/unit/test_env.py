from lakehouse.config import Settings


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GCP_REGION", raising=False)
    monkeypatch.delenv("GCP_LOCATION", raising=False)
    monkeypatch.delenv("GCS_BUCKET_NAME", raising=False)
    for variable in (
        "BQ_DATASET_BRONZE",
        "BQ_DATASET_SILVER",
        "BQ_DATASET_GOLD",
        "BQ_DATASET_OPS",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.delenv("PIPELINE_NAME", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DBT_TARGET", raising=False)
    monkeypatch.delenv("CLOUD_LOGGING_ENABLED", raising=False)

    settings = Settings.from_env()

    assert settings.project_id == ""
    assert settings.region == "southamerica-east1"
    assert settings.location == "southamerica-east1"
    assert settings.gcs_bucket_name == ""
    assert settings.bq_dataset_bronze == "bronze"
    assert settings.bq_dataset_silver == "silver"
    assert settings.bq_dataset_gold == "gold"
    assert settings.bq_dataset_ops == "ops"
    assert settings.pipeline_name == "lakehouse-financeiro"
    assert settings.log_level == "INFO"
    assert settings.dbt_target == "dev"
    assert settings.cloud_logging_enabled is False


def test_settings_from_env_overrides(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "projeto-teste")
    monkeypatch.setenv("GCP_REGION", "southamerica-east1")
    monkeypatch.setenv("GCS_BUCKET_NAME", "bucket-teste")
    monkeypatch.setenv("BQ_DATASET_BRONZE", "bronze_teste")
    monkeypatch.setenv("BQ_DATASET_OPS", "ops_teste")
    monkeypatch.setenv("PIPELINE_NAME", "demo")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DBT_TARGET", "prod")
    monkeypatch.setenv("CLOUD_LOGGING_ENABLED", "true")

    settings = Settings.from_env()

    assert settings.project_id == "projeto-teste"
    assert settings.gcs_bucket_name == "bucket-teste"
    assert settings.bq_dataset_bronze == "bronze_teste"
    assert settings.bq_dataset_ops == "ops_teste"
    assert settings.pipeline_name == "demo"
    assert settings.log_level == "DEBUG"
    assert settings.dbt_target == "prod"
    assert settings.cloud_logging_enabled is True
