from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

from google.cloud import bigquery

from lakehouse.config import Settings
from lakehouse.observability import configure_logging

LOGGER = logging.getLogger(__name__)

ENTITIES = ("customers", "contracts", "installments")
SILVER_TABLES = tuple(f"silver_{entity}" for entity in ENTITIES)
BRONZE_TABLE_MAP = dict(zip(ENTITIES, ENTITIES))
SILVER_TABLE_MAP = dict(zip(ENTITIES, SILVER_TABLES))
STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"


def target_dataset(base: str, target: str) -> str:
    return base if target == "prod" else f"{base}_{target}"


def table_ref(project: str, dataset: str, table: str) -> str:
    return f"`{project}.{dataset}.{table}`"


def date_param(value: date) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter("ingestion_date", "DATE", value)


def get_batch_ids(
    client: bigquery.Client, settings: Settings, ingestion_date: date
) -> dict[str, str]:
    query = f"""
        SELECT entity, batch_id
        FROM {table_ref(settings.project_id, settings.bq_dataset_ops, "ingestion_batches")}
        WHERE ingestion_date = @ingestion_date AND status = 'SUCCEEDED'
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[date_param(ingestion_date)])
    rows = client.query(query, job_config=job_config).result()
    return {row["entity"]: row["batch_id"] for row in rows}


def get_counts(
    client: bigquery.Client,
    settings: Settings,
    ingestion_date: date,
    dataset: str,
    tables: Mapping[str, str],
) -> dict[str, int]:
    selects = [
        (
            f"SELECT '{entity}' AS entity, COUNT(*) AS total "
            f"FROM {table_ref(settings.project_id, dataset, table_name)} "
            "WHERE ingestion_date = @ingestion_date"
        )
        for entity, table_name in tables.items()
    ]
    query = " UNION ALL ".join(selects)
    job_config = bigquery.QueryJobConfig(query_parameters=[date_param(ingestion_date)])
    rows = client.query(query, job_config=job_config).result()
    return {row["entity"]: int(row["total"]) for row in rows}


def parse_run_results(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    summary: dict[str, object] = {
        "invocation_id": payload.get("metadata", {}).get("invocation_id", ""),
        "pass": 0,
        "warn": 0,
        "fail": 0,
        "error": 0,
        "skipped": 0,
        "execution_time_seconds": 0.0,
        "rows_affected": 0,
        "model_pass": 0,
        "model_error": 0,
    }
    for result in payload.get("results", []):
        unique_id = str(result.get("unique_id", ""))
        status = str(result.get("status", "")).lower()
        summary["execution_time_seconds"] = float(summary["execution_time_seconds"]) + float(
            result.get("execution_time", 0) or 0
        )
        if unique_id.startswith("test.") and status in {
            "pass",
            "warn",
            "fail",
            "error",
            "skipped",
        }:
            summary[status] = int(summary[status]) + 1
        if unique_id.startswith("model."):
            key = "model_pass" if status in {"success", "pass"} else "model_error"
            summary[key] = int(summary[key]) + 1
            adapter_response = result.get("adapter_response") or {}
            summary["rows_affected"] = int(summary["rows_affected"]) + int(
                adapter_response.get("rows_affected", 0) or 0
            )
    return summary


def parse_manifest(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text())
    nodes = payload.get("nodes", {})
    return {
        "models": sum(node.get("resource_type") == "model" for node in nodes.values()),
        "tests": sum(node.get("resource_type") == "test" for node in nodes.values()),
        "sources": len(payload.get("sources", {})),
    }


def parse_freshness(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    statuses: list[str] = []
    ages: list[float] = []
    sources = payload.get("results") or payload.get("sources") or []
    for source in sources:
        freshness = source.get("freshness") or source
        status = str(freshness.get("status", "")).lower()
        if status:
            statuses.append(status)
        age = freshness.get("age")
        if age is None:
            age = source.get("max_loaded_at_time_ago_in_s")
        if age is not None:
            ages.append(float(age))
    if "error" in statuses:
        status = "error"
    elif "warn" in statuses:
        status = "warn"
    elif statuses and all(item == "pass" for item in statuses):
        status = "pass"
    else:
        status = "error"
    max_age_hours = round(max(ages) / 3600, 2) if ages else 0.0
    return {"status": status, "max_age_hours": max_age_hours}


def make_row(
    ingestion_date: date,
    entity: str,
    batch_id: str,
    metric_name: str,
    metric_value: object,
    status: str,
    details: dict[str, object],
    checked_at: str,
) -> dict[str, str]:
    return {
        "ingestion_date": ingestion_date.isoformat(),
        "entity": entity,
        "batch_id": batch_id,
        "metric_name": metric_name,
        "metric_value": str(metric_value),
        "status": status,
        "details": json.dumps(details, sort_keys=True),
        "checked_at": checked_at,
    }


def build_rows(
    ingestion_date: date,
    batch_ids: dict[str, str],
    input_counts: dict[str, int],
    output_counts: dict[str, int],
    run_summary: dict[str, object],
    freshness_summary: dict[str, object],
    now: datetime | None = None,
) -> list[dict[str, str]]:
    moment = now or datetime.now(timezone.utc)
    checked_at = moment.isoformat().replace("+00:00", "Z")
    invocation_id = str(run_summary.get("invocation_id") or "dbt")
    rows: list[dict[str, str]] = []

    for entity in ENTITIES:
        batch_id = batch_ids.get(entity, "unknown")
        input_count = int(input_counts.get(entity, 0))
        output_count = int(output_counts.get(entity, 0))
        rejected_count = max(input_count - output_count, 0)
        metrics = (
            ("input_count", input_count, STATUS_PASS if input_count > 0 else STATUS_WARN),
            (
                "output_count",
                output_count,
                STATUS_PASS if output_count == input_count and input_count > 0 else STATUS_WARN,
            ),
            ("rejected_count", rejected_count, STATUS_PASS if rejected_count == 0 else STATUS_WARN),
        )
        for metric_name, metric_value, status in metrics:
            rows.append(
                make_row(
                    ingestion_date,
                    entity,
                    batch_id,
                    metric_name,
                    metric_value,
                    status,
                    {"batch_id": batch_id},
                    checked_at,
                )
            )

    passed = int(run_summary.get("pass", 0)) + int(run_summary.get("warn", 0))
    failed = int(run_summary.get("fail", 0)) + int(run_summary.get("error", 0))
    rows.append(
        make_row(
            ingestion_date,
            "dbt",
            invocation_id,
            "dbt_tests_passed",
            passed,
            STATUS_PASS,
            {"invocation_id": invocation_id},
            checked_at,
        )
    )
    rows.append(
        make_row(
            ingestion_date,
            "dbt",
            invocation_id,
            "dbt_tests_failed",
            failed,
            STATUS_PASS if failed == 0 else STATUS_FAIL,
            {"invocation_id": invocation_id},
            checked_at,
        )
    )

    freshness_status = str(freshness_summary.get("status", "error")).lower()
    mapped_status = {
        "pass": STATUS_PASS,
        "warn": STATUS_WARN,
        "error": STATUS_FAIL,
    }.get(freshness_status, STATUS_FAIL)
    rows.append(
        make_row(
            ingestion_date,
            "bronze",
            invocation_id,
            "source_freshness_max_age_hours",
            freshness_summary.get("max_age_hours", 0.0),
            mapped_status,
            {"warn_after_hours": 72, "error_after_hours": 168},
            checked_at,
        )
    )
    return rows


def collect_rows(
    client: bigquery.Client,
    settings: Settings,
    ingestion_date: date,
    run_results_path: Path,
    freshness_path: Path,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    silver_dataset = target_dataset(settings.bq_dataset_silver, settings.dbt_target)
    return build_rows(
        ingestion_date,
        get_batch_ids(client, settings, ingestion_date),
        get_counts(
            client, settings, ingestion_date, settings.bq_dataset_bronze, BRONZE_TABLE_MAP
        ),
        get_counts(client, settings, ingestion_date, silver_dataset, SILVER_TABLE_MAP),
        parse_run_results(run_results_path),
        parse_freshness(freshness_path),
        now,
    )


def write_rows(
    client: bigquery.Client,
    settings: Settings,
    ingestion_date: date,
    rows: list[dict[str, str]],
) -> None:
    table = (
        f"{settings.project_id}.{settings.bq_dataset_ops}.dq_results"
        f"${ingestion_date:%Y%m%d}"
    )
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=False,
    )
    job = client.load_table_from_json(rows, table, job_config=job_config)
    job.result()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Resumo de qualidade da Fase 7")
    parser.add_argument("--ingestion-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--run-results",
        type=Path,
        default=Path("dbt/target/run_results.json"),
    )
    parser.add_argument(
        "--freshness",
        type=Path,
        default=Path("dbt/target/sources.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("dbt/target/manifest.json"),
    )
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if not settings.project_id:
        raise SystemExit("GCP_PROJECT_ID não configurado")
    configure_logging(
        level=settings.log_level,
        project_id=settings.project_id,
        cloud_enabled=settings.cloud_logging_enabled,
    )
    started = perf_counter()
    try:
        client = bigquery.Client(project=settings.project_id, location=settings.location)
        rows = collect_rows(
            client,
            settings,
            args.ingestion_date,
            args.run_results,
            args.freshness,
        )
        write_rows(client, settings, args.ingestion_date, rows)
        run_summary = parse_run_results(args.run_results)
        manifest_summary = parse_manifest(args.manifest) if args.manifest.exists() else {}
        freshness_summary = parse_freshness(args.freshness)
        batch_ids = sorted({row["batch_id"] for row in rows if row["entity"] != "dbt"})
        failed = any(row["status"] == STATUS_FAIL for row in rows)
        log = LOGGER.error if failed else LOGGER.info
        log(
            "pipeline.stage_summary",
            extra={
                "pipeline_name": settings.pipeline_name,
                "stage": "quality",
                "status": "failure" if failed else "success",
                "ingestion_date": args.ingestion_date.isoformat(),
                "batch_ids": batch_ids,
                "invocation_id": run_summary["invocation_id"],
                "quality_row_count": len(rows),
                "dbt_tests_passed": run_summary["pass"],
                "dbt_tests_failed": int(run_summary["fail"]) + int(run_summary["error"]),
                "dbt_models_passed": run_summary["model_pass"],
                "dbt_models_failed": run_summary["model_error"],
                "dbt_execution_time_seconds": round(
                    float(run_summary["execution_time_seconds"]), 3
                ),
                "dbt_rows_affected": run_summary["rows_affected"],
                "manifest": manifest_summary,
                "source_freshness_status": freshness_summary["status"],
                "duration_seconds": round(perf_counter() - started, 3),
            },
        )
    except Exception as exc:
        LOGGER.error(
            "pipeline.failed",
            extra={
                "pipeline_name": settings.pipeline_name,
                "stage": "quality",
                "status": "failure",
                "ingestion_date": args.ingestion_date.isoformat(),
                "error": str(exc),
                "duration_seconds": round(perf_counter() - started, 3),
            },
        )
        raise


if __name__ == "__main__":
    main()
