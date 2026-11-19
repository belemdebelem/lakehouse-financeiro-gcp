import json
from datetime import date, datetime, timezone

from google.cloud import bigquery

from lakehouse.config import Settings
from lakehouse.quality import (
    SILVER_TABLE_MAP,
    build_rows,
    get_counts,
    parse_freshness,
    parse_run_results,
    target_dataset,
    write_rows,
)

INGESTION_DATE = date(2026, 11, 17)
NOW = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)


def test_target_dataset_isolates_non_prod_runs():
    assert target_dataset("silver", "dev") == "silver_dev"
    assert target_dataset("silver", "prod") == "silver"


def test_parse_run_results_counts_only_tests(tmp_path):
    path = tmp_path / "run_results.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"invocation_id": "inv-123"},
                "results": [
                    {"unique_id": "model.pkg.silver_customers", "status": "pass"},
                    {"unique_id": "test.pkg.not_null_1", "status": "pass"},
                    {"unique_id": "test.pkg.unique_1", "status": "fail"},
                    {"unique_id": "test.pkg.accepted_1", "status": "warn"},
                ],
            }
        )
    )

    summary = parse_run_results(path)

    assert summary["invocation_id"] == "inv-123"
    assert summary["pass"] == 1
    assert summary["fail"] == 1
    assert summary["warn"] == 1
    assert summary["error"] == 0


def test_parse_freshness_uses_worst_status_and_max_age(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "results": [
                    {"status": "pass", "max_loaded_at_time_ago_in_s": 3600},
                    {"status": "warn", "max_loaded_at_time_ago_in_s": 180000},
                ]
            }
        )
    )

    summary = parse_freshness(path)

    assert summary["status"] == "warn"
    assert summary["max_age_hours"] == 50.0


def test_build_rows_records_counts_rejections_tests_and_freshness():
    rows = build_rows(
        INGESTION_DATE,
        {"customers": "b1", "contracts": "b2", "installments": "b3"},
        {"customers": 10, "contracts": 13, "installments": 79},
        {"customers": 10, "contracts": 13, "installments": 78},
        {"invocation_id": "inv-123", "pass": 76, "warn": 1, "fail": 0, "error": 0},
        {"status": "pass", "max_age_hours": 48.5},
        NOW,
    )

    assert len(rows) == 12
    assert all(row["checked_at"] == "2026-11-19T21:00:00Z" for row in rows)
    rejection = next(
        row
        for row in rows
        if row["entity"] == "installments" and row["metric_name"] == "rejected_count"
    )
    assert rejection["metric_value"] == "1"
    assert rejection["status"] == "WARN"
    assert rejection["batch_id"] == "b3"
    failed = next(row for row in rows if row["metric_name"] == "dbt_tests_failed")
    assert failed["metric_value"] == "0"
    assert failed["status"] == "PASS"
    freshness = next(
        row for row in rows if row["metric_name"] == "source_freshness_max_age_hours"
    )
    assert freshness["metric_value"] == "48.5"
    assert freshness["status"] == "PASS"


class FakeJob:
    def result(self):
        return []


class FakeClient:
    def __init__(self) -> None:
        self.queries: list[dict] = []
        self.loads: list[tuple[str, list[dict[str, str]], bigquery.LoadJobConfig]] = []

    def query(self, sql, job_config=None):
        self.queries.append({"sql": sql, "job_config": job_config})
        return FakeJob()

    def load_table_from_json(self, rows, table, job_config=None):
        self.loads.append((table, rows, job_config))
        return FakeJob()


def test_get_counts_uses_silver_model_names():
    settings = Settings(
        project_id="projeto-teste",
        region="southamerica-east1",
        location="southamerica-east1",
        gcs_bucket_name="bucket-teste",
        bq_dataset_bronze="bronze",
        bq_dataset_silver="silver",
        bq_dataset_gold="gold",
        bq_dataset_ops="ops",
        pipeline_name="demo",
        log_level="INFO",
    )
    client = FakeClient()

    get_counts(client, settings, INGESTION_DATE, "silver_dev", SILVER_TABLE_MAP)

    sql = client.queries[0]["sql"]
    assert "silver_dev.silver_customers" in sql
    assert "silver_dev.silver_contracts" in sql
    assert "silver_dev.silver_installments" in sql


def test_write_rows_replaces_ingestion_date_partition():
    settings = Settings(
        project_id="projeto-teste",
        region="southamerica-east1",
        location="southamerica-east1",
        gcs_bucket_name="bucket-teste",
        bq_dataset_bronze="bronze",
        bq_dataset_silver="silver",
        bq_dataset_gold="gold",
        bq_dataset_ops="ops",
        pipeline_name="demo",
        log_level="INFO",
    )
    client = FakeClient()
    rows = [{"metric_name": "input_count"}]

    write_rows(client, settings, INGESTION_DATE, rows)

    assert client.queries == []
    assert len(client.loads) == 1
    table, loaded_rows, job_config = client.loads[0]
    assert table == "projeto-teste.ops.dq_results$20261117"
    assert loaded_rows == rows
    assert job_config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    assert job_config.source_format == bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
