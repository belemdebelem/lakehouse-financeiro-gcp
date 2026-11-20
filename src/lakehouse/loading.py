"""Carga batch do GCS para a camada Bronze do BigQuery (Fase 5)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any

from google.cloud import bigquery, storage

from lakehouse.config import Settings
from lakehouse.ingestion import build_object_path
from lakehouse.observability import configure_logging

LOGGER = logging.getLogger(__name__)

SOURCE_FIELDS: dict[str, tuple[bigquery.SchemaField, ...]] = {
    "customers": (
        bigquery.SchemaField("customer_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("customer_segment", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ),
    "contracts": (
        bigquery.SchemaField("contract_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("customer_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("product_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("principal_amount", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("annual_interest_rate", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("start_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("end_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ),
    "installments": (
        bigquery.SchemaField("contract_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("installment_number", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("due_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("paid_at", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("amount_due", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("amount_paid", "NUMERIC", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ),
}

BUSINESS_KEYS: dict[str, tuple[str, ...]] = {
    "customers": ("customer_id",),
    "contracts": ("contract_id",),
    "installments": ("contract_id", "installment_number"),
}

METADATA_FIELDS = ("batch_id", "source_file", "ingested_at", "ingestion_date")
STATUS_STARTED = "STARTED"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"


class LoadError(Exception):
    pass


@dataclass(frozen=True)
class EntityLoadResult:
    entity: str
    batch_id: str
    source_file: str
    row_count: int
    status: str


@dataclass(frozen=True)
class BronzeLoadResult:
    ingestion_date: date
    loads: tuple[EntityLoadResult, ...]


def _log(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    logger.log(level, event, extra=fields)


def _table_ref(project: str, dataset: str, table: str) -> str:
    return f"`{project}.{dataset}.{table}`"


def _batch_state_sql(project: str, ops_dataset: str) -> str:
    table = _table_ref(project, ops_dataset, "ingestion_batches")
    return f"""
MERGE {table} T
USING (SELECT @batch_id AS batch_id, @entity AS entity) S
ON T.batch_id = S.batch_id AND T.entity = S.entity
WHEN MATCHED THEN UPDATE SET
  source_file = @source_file,
  row_count = @row_count,
  status = @status,
  error = @error,
  finished_at = @finished_at
WHEN NOT MATCHED THEN INSERT (
  batch_id, entity, source_file, row_count, status, error,
  started_at, finished_at, ingestion_date
) VALUES (
  @batch_id, @entity, @source_file, @row_count, @status, @error,
  @started_at, @finished_at, @ingestion_date
)
"""


def _merge_sql(project: str, bronze_dataset: str, entity: str) -> str:
    target = _table_ref(project, bronze_dataset, entity)
    source = _table_ref(project, bronze_dataset, f"{entity}_staging")
    columns = [field.name for field in SOURCE_FIELDS[entity]]
    on_clause = " AND ".join(f"T.{key} = S.{key}" for key in BUSINESS_KEYS[entity])
    update_clause = ", ".join([f"T.{column} = S.{column}" for column in columns] + [
        "T.batch_id = @batch_id",
        "T.source_file = @source_file",
        "T.ingested_at = @ingested_at",
        "T.ingestion_date = @ingestion_date",
    ])
    insert_columns = ", ".join(columns + list(METADATA_FIELDS))
    insert_values = ", ".join([
        *(f"S.{column}" for column in columns),
        "@batch_id",
        "@source_file",
        "@ingested_at",
        "@ingestion_date",
    ])
    return f"""
MERGE {target} T
USING {source} S
ON {on_clause}
WHEN MATCHED THEN UPDATE SET {update_clause}
WHEN NOT MATCHED THEN INSERT ({insert_columns}) VALUES ({insert_values})
"""


def _batch_state_params(
    batch_id: str,
    entity: str,
    source_file: str,
    row_count: int,
    status: str,
    error: str | None,
    started_at: datetime,
    finished_at: datetime | None,
    ingestion_date: date,
) -> list[bigquery.ScalarQueryParameter]:
    return [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        bigquery.ScalarQueryParameter("entity", "STRING", entity),
        bigquery.ScalarQueryParameter("source_file", "STRING", source_file),
        bigquery.ScalarQueryParameter("row_count", "INT64", row_count),
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("error", "STRING", error),
        bigquery.ScalarQueryParameter("started_at", "TIMESTAMP", started_at),
        bigquery.ScalarQueryParameter("finished_at", "TIMESTAMP", finished_at),
        bigquery.ScalarQueryParameter("ingestion_date", "DATE", ingestion_date),
    ]


def _write_batch_state(
    bq_client: Any,
    settings: Settings,
    *,
    batch_id: str,
    entity: str,
    source_file: str,
    row_count: int,
    status: str,
    error: str | None,
    started_at: datetime,
    finished_at: datetime | None,
    ingestion_date: date,
) -> None:
    params = _batch_state_params(
        batch_id,
        entity,
        source_file,
        row_count,
        status,
        error,
        started_at,
        finished_at,
        ingestion_date,
    )
    query = _batch_state_sql(settings.project_id, settings.bq_dataset_ops)
    bq_client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def _already_succeeded(
    bq_client: Any,
    settings: Settings,
    batch_id: str,
    entity: str,
) -> bool:
    query = f"""
SELECT status
FROM {_table_ref(settings.project_id, settings.bq_dataset_ops, 'ingestion_batches')}
WHERE batch_id = @batch_id AND entity = @entity
"""
    params = [
        bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
        bigquery.ScalarQueryParameter("entity", "STRING", entity),
    ]
    rows = list(
        bq_client.query(
            query,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
    )
    return bool(rows and rows[0]["status"] == STATUS_SUCCEEDED)


def load_bronze_from_gcs(
    settings: Settings,
    ingestion_date: date,
    *,
    bq_client: Any | None = None,
    storage_client: Any | None = None,
    now: datetime | None = None,
    logger: logging.Logger | None = None,
    entities: tuple[str, ...] | None = None,
) -> BronzeLoadResult:
    if not settings.gcs_bucket_name:
        raise LoadError("GCS_BUCKET_NAME não configurado")

    log = logger or LOGGER
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    selected = entities or tuple(SOURCE_FIELDS)

    bq = bq_client or bigquery.Client(project=settings.project_id, location=settings.region)
    gcs = storage_client or storage.Client(project=settings.project_id)
    bucket = gcs.bucket(settings.gcs_bucket_name)

    _log(
        log,
        logging.INFO,
        "bronze_load.started",
        pipeline_name=settings.pipeline_name,
        stage="bronze_load",
        status=STATUS_STARTED,
        project_id=settings.project_id,
        bucket_name=settings.gcs_bucket_name,
        bronze_dataset=settings.bq_dataset_bronze,
        ops_dataset=settings.bq_dataset_ops,
        ingestion_date=ingestion_date.isoformat(),
        entity_count=len(selected),
    )

    loads: list[EntityLoadResult] = []
    for entity in selected:
        source_file = build_object_path(entity, f"{entity}.csv", ingestion_date)
        blob = bucket.blob(source_file)
        try:
            blob.reload()
        except Exception as exc:
            raise LoadError(f"falha ao ler metadados de {source_file}: {exc}") from exc
        metadata = blob.metadata or {}
        batch_id = metadata.get("batch_id", "")
        source_file = metadata.get("source_file", source_file)
        row_count = int(metadata.get("row_count", "0"))
        if not batch_id:
            raise LoadError(f"metadados de lote ausentes em {source_file}")
        if metadata.get("ingestion_date") != ingestion_date.isoformat():
            raise LoadError(f"ingestion_date inconsistente em {source_file}")

        if _already_succeeded(bq, settings, batch_id, entity):
            _log(
                log,
                logging.INFO,
                "bronze_load.skipped",
                pipeline_name=settings.pipeline_name,
                stage="bronze_load",
                status=STATUS_SUCCEEDED,
                batch_id=batch_id,
                entity=entity,
                source_file=source_file,
                row_count=row_count,
            )
            loads.append(
                EntityLoadResult(
                    entity=entity,
                    batch_id=batch_id,
                    source_file=source_file,
                    row_count=row_count,
                    status=STATUS_SUCCEEDED,
                )
            )
            continue

        _write_batch_state(
            bq,
            settings,
            batch_id=batch_id,
            entity=entity,
            source_file=source_file,
            row_count=row_count,
            status=STATUS_STARTED,
            error=None,
            started_at=current_time,
            finished_at=None,
            ingestion_date=ingestion_date,
        )

        try:
            staging_table = (
                f"{settings.project_id}.{settings.bq_dataset_bronze}.{entity}_staging"
            )
            load_config = bigquery.LoadJobConfig(
                schema=SOURCE_FIELDS[entity],
                source_format=bigquery.SourceFormat.CSV,
                skip_leading_rows=1,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                max_bad_records=0,
                ignore_unknown_values=False,
            )
            uri = f"gs://{settings.gcs_bucket_name}/{source_file}"
            load_job = bq.load_table_from_uri(uri, staging_table, job_config=load_config)
            load_job.result()
            loaded_rows = load_job.output_rows or row_count

            merge_query = _merge_sql(
                settings.project_id,
                settings.bq_dataset_bronze,
                entity,
            )
            merge_params = [
                bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id),
                bigquery.ScalarQueryParameter("source_file", "STRING", source_file),
                bigquery.ScalarQueryParameter("ingested_at", "TIMESTAMP", current_time),
                bigquery.ScalarQueryParameter("ingestion_date", "DATE", ingestion_date),
            ]
            bq.query(
                merge_query,
                job_config=bigquery.QueryJobConfig(query_parameters=merge_params),
            ).result()
        except Exception as exc:
            _log(
                log,
                logging.ERROR,
                "bronze_load.failed",
                pipeline_name=settings.pipeline_name,
                stage="bronze_load",
                status=STATUS_FAILED,
                batch_id=batch_id,
                entity=entity,
                source_file=source_file,
                error=str(exc),
            )
            try:
                _write_batch_state(
                    bq,
                    settings,
                    batch_id=batch_id,
                    entity=entity,
                    source_file=source_file,
                    row_count=row_count,
                    status=STATUS_FAILED,
                    error=str(exc),
                    started_at=current_time,
                    finished_at=current_time,
                    ingestion_date=ingestion_date,
                )
            except Exception as state_exc:
                _log(
                    log,
                    logging.ERROR,
                    "bronze_load.state_update_failed",
                    pipeline_name=settings.pipeline_name,
                    stage="bronze_load",
                    status=STATUS_FAILED,
                    batch_id=batch_id,
                    entity=entity,
                    error=str(state_exc),
                )
            raise LoadError(f"falha ao carregar {entity}: {exc}") from exc

        _write_batch_state(
            bq,
            settings,
            batch_id=batch_id,
            entity=entity,
            source_file=source_file,
            row_count=loaded_rows,
            status=STATUS_SUCCEEDED,
            error=None,
            started_at=current_time,
            finished_at=current_time,
            ingestion_date=ingestion_date,
        )
        _log(
            log,
            logging.INFO,
            "bronze_load.loaded",
            pipeline_name=settings.pipeline_name,
            stage="bronze_load",
            status=STATUS_SUCCEEDED,
            batch_id=batch_id,
            entity=entity,
            source_file=source_file,
            row_count=loaded_rows,
        )
        loads.append(
            EntityLoadResult(
                entity=entity,
                batch_id=batch_id,
                source_file=source_file,
                row_count=loaded_rows,
                status=STATUS_SUCCEEDED,
            )
        )

    _log(
        log,
        logging.INFO,
        "bronze_load.completed",
        pipeline_name=settings.pipeline_name,
        stage="bronze_load",
        status=STATUS_SUCCEEDED,
        ingestion_date=ingestion_date.isoformat(),
        loaded_count=len(loads),
    )
    return BronzeLoadResult(ingestion_date=ingestion_date, loads=tuple(loads))


def main() -> None:
    settings = Settings.from_env()
    configure_logging(
        level=settings.log_level,
        project_id=settings.project_id,
        cloud_enabled=settings.cloud_logging_enabled,
    )
    default_date = datetime.now(timezone.utc).date()
    ingestion_date = date.fromisoformat(os.getenv("INGESTION_DATE", default_date.isoformat()))
    started = perf_counter()
    try:
        result = load_bronze_from_gcs(settings, ingestion_date)
    except Exception as exc:
        _log(
            LOGGER,
            logging.ERROR,
            "pipeline.failed",
            pipeline_name=settings.pipeline_name,
            stage="bronze_load",
            status="failure",
            ingestion_date=ingestion_date.isoformat(),
            error=str(exc),
            duration_seconds=round(perf_counter() - started, 3),
        )
        raise
    _log(
        LOGGER,
        logging.INFO,
        "pipeline.stage_summary",
        pipeline_name=settings.pipeline_name,
        stage="bronze_load",
        status="success",
        ingestion_date=ingestion_date.isoformat(),
        batch_ids=[item.batch_id for item in result.loads],
        row_count=sum(item.row_count for item in result.loads),
        entity_count=len(result.loads),
        duration_seconds=round(perf_counter() - started, 3),
    )


if __name__ == "__main__":
    main()
