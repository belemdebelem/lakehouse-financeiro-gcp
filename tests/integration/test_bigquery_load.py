import os
from datetime import date
from pathlib import Path

import pytest
from google.cloud import bigquery

from lakehouse.config import Settings
from lakehouse.loading import STATUS_SUCCEEDED, load_bronze_from_gcs

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BQ_INTEGRATION") != "1",
    reason="integração com BigQuery é opt-in via RUN_BQ_INTEGRATION=1",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_DATE = date(2026, 11, 17)


def test_bigquery_load_is_idempotent():
    settings = Settings.from_env()
    if not settings.gcs_bucket_name:
        pytest.skip("GCS_BUCKET_NAME não configurado")

    result = load_bronze_from_gcs(settings, INGESTION_DATE)
    assert len(result.loads) == 3
    assert {load.entity for load in result.loads} == {
        "customers",
        "contracts",
        "installments",
    }
    assert all(load.status == STATUS_SUCCEEDED for load in result.loads)

    bq_client = bigquery.Client(project=settings.project_id, location=settings.region)
    for load in result.loads:
        table = f"`{settings.project_id}.{settings.bq_dataset_bronze}.{load.entity}`"
        query = f"SELECT COUNT(*) AS total FROM {table} WHERE batch_id = @batch_id"
        params = [
            bigquery.ScalarQueryParameter("batch_id", "STRING", load.batch_id),
        ]
        rows = list(
            bq_client.query(
                query,
                job_config=bigquery.QueryJobConfig(query_parameters=params),
            ).result()
        )
        assert rows[0]["total"] == load.row_count

    repeated = load_bronze_from_gcs(settings, INGESTION_DATE)
    assert [load.status for load in repeated.loads] == [STATUS_SUCCEEDED] * 3
