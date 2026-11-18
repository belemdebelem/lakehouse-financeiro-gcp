import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from google.cloud import bigquery

from lakehouse.config import Settings
from lakehouse.ingestion import build_batch_id, build_object_path
from lakehouse.loading import (
    SOURCE_FIELDS,
    STATUS_FAILED,
    STATUS_STARTED,
    STATUS_SUCCEEDED,
    LoadError,
    _merge_sql,
    load_bronze_from_gcs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_DATE = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
BUCKET = "bucket-teste"


class FakeJob:
    def __init__(self, rows=None, output_rows=None) -> None:
        self.rows = rows or []
        self.output_rows = output_rows

    def result(self):
        return self.rows


class FakeBigQueryClient:
    def __init__(
        self,
        *,
        succeeded: set[tuple[str, str]] | None = None,
        fail_merge: bool = False,
    ) -> None:
        self.succeeded = succeeded or set()
        self.fail_merge = fail_merge
        self.loads: list[dict] = []
        self.queries: list[dict] = []
        self.state_writes: list[dict] = []

    def query(self, sql: str, job_config=None):
        self.queries.append({"sql": sql, "job_config": job_config})
        params = {param.name: param.value for param in job_config.query_parameters}
        if "SELECT status" in sql:
            key = (params["batch_id"], params["entity"])
            rows = [{"status": STATUS_SUCCEEDED}] if key in self.succeeded else []
            return FakeJob(rows)
        if "ingestion_batches" in sql:
            self.state_writes.append(params)
            return FakeJob()
        if self.fail_merge:
            raise RuntimeError("merge indisponível")
        return FakeJob()

    def load_table_from_uri(self, uri: str, table_ref: str, job_config=None):
        self.loads.append(
            {"uri": uri, "table_ref": table_ref, "job_config": job_config}
        )
        return FakeJob(output_rows=10)


class FakeBlob:
    def __init__(self, metadata: dict[str, str]) -> None:
        self.metadata = metadata

    def reload(self) -> None:
        return None


class FakeStorageBucket:
    def __init__(self, metadata_by_path: dict[str, dict[str, str]]) -> None:
        self.metadata_by_path = metadata_by_path

    def blob(self, path: str) -> FakeBlob:
        return FakeBlob(self.metadata_by_path[path])


class FakeStorageClient:
    def __init__(self, metadata_by_path: dict[str, dict[str, str]]) -> None:
        self.metadata_by_path = metadata_by_path

    def bucket(self, name: str) -> FakeStorageBucket:
        assert name == BUCKET
        return FakeStorageBucket(self.metadata_by_path)


def make_settings() -> Settings:
    return Settings(
        project_id="projeto-teste",
        region="southamerica-east1",
        location="southamerica-east1",
        gcs_bucket_name=BUCKET,
        bq_dataset_bronze="bronze",
        bq_dataset_silver="silver",
        bq_dataset_gold="gold",
        bq_dataset_ops="ops",
        pipeline_name="demo",
        log_level="INFO",
    )


def make_metadata(entity: str, batch_id: str | None = None) -> dict[str, str]:
    object_path = build_object_path(entity, f"{entity}.csv", INGESTION_DATE)
    return {
        "batch_id": batch_id or build_batch_id(entity, "abc123"),
        "source_file": object_path,
        "ingestion_date": INGESTION_DATE.isoformat(),
        "row_count": "10",
        "sha256": "abc123",
    }


def make_storage(entities: tuple[str, ...]) -> FakeStorageClient:
    return FakeStorageClient(
        {
            build_object_path(entity, f"{entity}.csv", INGESTION_DATE): make_metadata(
                entity
            )
            for entity in entities
        }
    )


def test_schemas_are_explicit_and_merge_uses_metadata():
    assert [field.name for field in SOURCE_FIELDS["customers"]] == [
        "customer_id",
        "customer_segment",
        "created_at",
        "updated_at",
    ]
    assert SOURCE_FIELDS["installments"][3].mode == "NULLABLE"
    merge = _merge_sql("projeto-teste", "bronze", "installments")
    assert "T.contract_id = S.contract_id" in merge
    assert "T.installment_number = S.installment_number" in merge
    assert "@batch_id" in merge
    assert "@source_file" in merge
    assert "@ingested_at" in merge
    assert "@ingestion_date" in merge


def test_loads_all_entities_and_records_state(caplog):
    entities = tuple(SOURCE_FIELDS)
    bq = FakeBigQueryClient()
    storage_client = make_storage(entities)

    with caplog.at_level(logging.INFO):
        result = load_bronze_from_gcs(
            make_settings(),
            INGESTION_DATE,
            bq_client=bq,
            storage_client=storage_client,
            now=NOW,
        )

    assert len(result.loads) == 3
    assert {load.entity for load in result.loads} == set(entities)
    assert all(load.status == STATUS_SUCCEEDED for load in result.loads)
    assert len(bq.loads) == 3
    assert all(
        call["job_config"].write_disposition
        == bigquery.WriteDisposition.WRITE_TRUNCATE
        for call in bq.loads
    )
    assert all(call["job_config"].max_bad_records == 0 for call in bq.loads)
    assert {call["table_ref"] for call in bq.loads} == {
        "projeto-teste.bronze.customers_staging",
        "projeto-teste.bronze.contracts_staging",
        "projeto-teste.bronze.installments_staging",
    }
    statuses = [write["status"] for write in bq.state_writes]
    assert statuses.count(STATUS_STARTED) == 3
    assert statuses.count(STATUS_SUCCEEDED) == 3
    assert any(record.message == "bronze_load.loaded" for record in caplog.records)
    loaded_logs = [
        record for record in caplog.records if record.message == "bronze_load.loaded"
    ]
    assert all(record.pipeline_name == "demo" for record in loaded_logs)
    assert all(record.stage == "bronze_load" for record in loaded_logs)
    assert all(hasattr(record, "batch_id") for record in loaded_logs)


def test_succeeded_batch_is_skipped_without_new_load():
    entity = "customers"
    metadata = make_metadata(entity)
    batch_id = metadata["batch_id"]
    bq = FakeBigQueryClient(succeeded={(batch_id, entity)})
    storage_client = FakeStorageClient(
        {build_object_path(entity, f"{entity}.csv", INGESTION_DATE): metadata}
    )

    result = load_bronze_from_gcs(
        make_settings(),
        INGESTION_DATE,
        bq_client=bq,
        storage_client=storage_client,
        now=NOW,
        entities=(entity,),
    )

    assert result.loads[0].status == STATUS_SUCCEEDED
    assert bq.loads == []
    assert bq.state_writes == []


def test_failed_merge_is_recorded_as_failed():
    entity = "customers"
    bq = FakeBigQueryClient(fail_merge=True)
    storage_client = make_storage((entity,))

    with pytest.raises(LoadError, match="falha ao carregar customers"):
        load_bronze_from_gcs(
            make_settings(),
            INGESTION_DATE,
            bq_client=bq,
            storage_client=storage_client,
            now=NOW,
            entities=(entity,),
        )

    assert [write["status"] for write in bq.state_writes] == [
        STATUS_STARTED,
        STATUS_FAILED,
    ]
    assert bq.state_writes[-1]["error"]


def test_missing_batch_metadata_is_rejected():
    entity = "customers"
    metadata = make_metadata(entity)
    metadata.pop("batch_id")
    storage_client = FakeStorageClient(
        {build_object_path(entity, f"{entity}.csv", INGESTION_DATE): metadata}
    )

    with pytest.raises(LoadError, match="metadados de lote ausentes"):
        load_bronze_from_gcs(
            make_settings(),
            INGESTION_DATE,
            bq_client=FakeBigQueryClient(),
            storage_client=storage_client,
            now=NOW,
            entities=(entity,),
        )
