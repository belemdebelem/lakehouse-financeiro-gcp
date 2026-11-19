import os
from datetime import date
from pathlib import Path

import pytest
from google.cloud import bigquery

from lakehouse.config import Settings
from lakehouse.quality import collect_rows, write_rows

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DQ_INTEGRATION") != "1",
    reason="integração com BigQuery é opt-in via RUN_DQ_INTEGRATION=1",
)

INGESTION_DATE = date(2026, 11, 17)
RUN_RESULTS = Path("dbt/target/run_results.json")
FRESHNESS = Path("dbt/target/sources.json")


def test_dq_results_summary_is_idempotent():
    settings = Settings.from_env()
    if not settings.project_id:
        pytest.skip("GCP_PROJECT_ID não configurado")
    if not RUN_RESULTS.exists() or not FRESHNESS.exists():
        pytest.skip("artefatos dbt ausentes; execute dbt test e dbt source freshness")

    client = bigquery.Client(project=settings.project_id, location=settings.location)
    rows = collect_rows(client, settings, INGESTION_DATE, RUN_RESULTS, FRESHNESS)
    write_rows(client, settings, INGESTION_DATE, rows)

    table = f"`{settings.project_id}.{settings.bq_dataset_ops}.dq_results`"
    query = f"SELECT COUNT(*) AS total FROM {table} WHERE ingestion_date = @d"
    params = [bigquery.ScalarQueryParameter("d", "DATE", INGESTION_DATE)]
    first = list(
        client.query(
            query, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
    )[0]["total"]

    write_rows(client, settings, INGESTION_DATE, rows)
    second = list(
        client.query(
            query, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
    )[0]["total"]

    assert first == second == len(rows)
    assert all(row["status"] != "FAIL" for row in rows)
