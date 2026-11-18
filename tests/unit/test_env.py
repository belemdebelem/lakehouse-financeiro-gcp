from lakehouse.config import Settings


def test_settings_from_env_defaults(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GCP_REGION", raising=False)
    monkeypatch.delenv("GCP_LOCATION", raising=False)
    monkeypatch.delenv("GCS_BUCKET_NAME", raising=False)
    monkeypatch.delenv("PIPELINE_NAME", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = Settings.from_env()

    assert settings.project_id == ""
    assert settings.region == "southamerica-east1"
    assert settings.location == "southamerica-east1"
    assert settings.gcs_bucket_name == ""
    assert settings.pipeline_name == "lakehouse-financeiro"
    assert settings.log_level == "INFO"


def test_settings_from_env_overrides(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "projeto-teste")
    monkeypatch.setenv("GCP_REGION", "southamerica-east1")
    monkeypatch.setenv("GCS_BUCKET_NAME", "bucket-teste")
    monkeypatch.setenv("PIPELINE_NAME", "demo")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings.from_env()

    assert settings.project_id == "projeto-teste"
    assert settings.gcs_bucket_name == "bucket-teste"
    assert settings.pipeline_name == "demo"
    assert settings.log_level == "DEBUG"
