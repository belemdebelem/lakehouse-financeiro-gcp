import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from google.api_core.exceptions import PreconditionFailed

from lakehouse.config import Settings
from lakehouse.generation import DEFAULT_SEED, generate_dataset, write_dataset
from lakehouse.ingestion import (
    IngestionError,
    ObjectAlreadyExistsError,
    ReadError,
    ValidationError,
    build_batch_id,
    build_object_path,
    checksum,
    ingest_directory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INVALID_DIR = REPO_ROOT / "data" / "sample" / "invalid"
INGESTION_DATE = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


class FakeBlob:
    def __init__(self, name: str, client: "FakeClient") -> None:
        self.name = name
        self.client = client
        self.metadata: dict[str, str] = {}

    def upload_from_filename(
        self,
        filename: str,
        *,
        content_type: str,
        if_generation_match: int,
    ) -> None:
        self.client.calls.append(
            {
                "object_path": self.name,
                "filename": filename,
                "content_type": content_type,
                "metadata": dict(self.metadata),
                "if_generation_match": if_generation_match,
            }
        )
        if if_generation_match == 0 and self.name in self.client.store:
            raise PreconditionFailed("objeto já existe")
        self.client.store[self.name] = {
            "content": Path(filename).read_bytes(),
            "content_type": content_type,
            "metadata": dict(self.metadata),
        }


class FakeBucket:
    def __init__(self, client: "FakeClient") -> None:
        self.client = client

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(name, self.client)


class FakeClient:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.bucket_name: str | None = None

    def bucket(self, name: str) -> FakeBucket:
        self.bucket_name = name
        return FakeBucket(self)


def make_settings(bucket_name: str = "bucket-teste") -> Settings:
    return Settings(
        project_id="projeto-teste",
        region="southamerica-east1",
        location="southamerica-east1",
        gcs_bucket_name=bucket_name,
        bq_dataset_bronze="bronze",
        bq_dataset_silver="silver",
        bq_dataset_gold="gold",
        bq_dataset_ops="ops",
        pipeline_name="demo",
        log_level="INFO",
    )


def make_sample_dir(tmp_path: Path) -> Path:
    write_dataset(generate_dataset(DEFAULT_SEED), tmp_path)
    return tmp_path


def test_paths_and_batch_ids_are_stable(tmp_path: Path):
    source = tmp_path / "customers.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    value = checksum(source)

    assert checksum(source) == value
    assert build_object_path("customers", "customers.csv", INGESTION_DATE) == (
        "landing/customers/ingestion_date=2026-11-17/customers.csv"
    )
    assert build_batch_id("customers", value) == build_batch_id("customers", value)
    assert build_batch_id("customers", value) != build_batch_id("contracts", value)


def test_ingest_valid_dataset_uploads_all_entities(tmp_path: Path):
    source_dir = make_sample_dir(tmp_path)
    client = FakeClient()

    result = ingest_directory(
        source_dir,
        make_settings(),
        client=client,
        ingestion_date=INGESTION_DATE,
        now=NOW,
    )

    assert client.bucket_name == "bucket-teste"
    assert len(result.uploads) == 3
    assert {upload.entity for upload in result.uploads} == {
        "customers",
        "contracts",
        "installments",
    }
    assert len(client.calls) == 3
    assert all(call["if_generation_match"] == 0 for call in client.calls)
    assert all(call["content_type"] == "text/csv" for call in client.calls)
    for upload in result.uploads:
        stored = client.store[upload.object_path]
        assert stored["content"] == (source_dir / upload.source_file).read_bytes()
        assert stored["metadata"]["batch_id"] == upload.batch_id
        assert stored["metadata"]["sha256"] == upload.sha256
        assert stored["metadata"]["source_file"] == upload.object_path
        assert stored["metadata"]["ingestion_date"] == "2026-11-17"
        assert stored["metadata"]["ingested_at"] == "2026-11-17T12:00:00Z"
        assert int(stored["metadata"]["row_count"]) == upload.row_count


def test_invalid_dataset_is_rejected_without_upload():
    client = FakeClient()

    with pytest.raises(ValidationError) as excinfo:
        ingest_directory(
            INVALID_DIR,
            make_settings(),
            client=client,
            ingestion_date=INGESTION_DATE,
            now=NOW,
        )

    assert any("customer_id duplicado" in error for error in excinfo.value.errors)
    assert client.calls == []
    assert client.store == {}


def test_existing_object_is_not_overwritten(tmp_path: Path):
    source_dir = make_sample_dir(tmp_path)
    client = FakeClient()
    object_path = build_object_path("customers", "customers.csv", INGESTION_DATE)
    client.store[object_path] = {
        "content": b"conteudo-original",
        "content_type": "text/csv",
        "metadata": {"batch_id": "anterior"},
    }

    with pytest.raises(ObjectAlreadyExistsError) as excinfo:
        ingest_directory(
            source_dir,
            make_settings(),
            client=client,
            ingestion_date=INGESTION_DATE,
            now=NOW,
        )

    assert excinfo.value.object_path == object_path
    assert client.store[object_path]["content"] == b"conteudo-original"


def test_missing_bucket_name_is_rejected(tmp_path: Path):
    with pytest.raises(IngestionError, match="GCS_BUCKET_NAME"):
        ingest_directory(
            make_sample_dir(tmp_path),
            make_settings(""),
            client=FakeClient(),
            ingestion_date=INGESTION_DATE,
            now=NOW,
        )


def test_missing_source_file_is_rejected(tmp_path: Path):
    with pytest.raises(ReadError):
        ingest_directory(
            tmp_path,
            make_settings(),
            client=FakeClient(),
            ingestion_date=INGESTION_DATE,
            now=NOW,
        )


def test_logs_identify_batch_and_file(tmp_path: Path, caplog):
    with caplog.at_level(logging.INFO):
        ingest_directory(
            make_sample_dir(tmp_path),
            make_settings(),
            client=FakeClient(),
            ingestion_date=INGESTION_DATE,
            now=NOW,
        )

    uploads = [record for record in caplog.records if record.message == "ingestion.uploaded"]
    assert len(uploads) == 3
    assert all(record.pipeline_name == "demo" for record in uploads)
    assert all(record.stage == "ingestion" for record in uploads)
    assert all(record.status == "success" for record in uploads)
    assert all(hasattr(record, "batch_id") for record in uploads)
    assert all(hasattr(record, "source_file") for record in uploads)
    assert all(hasattr(record, "object_path") for record in uploads)
    assert {record.entity for record in uploads} == {
        "customers",
        "contracts",
        "installments",
    }
