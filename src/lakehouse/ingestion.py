"""Ingestão batch de CSVs sintéticos para o GCS (Fase 4)."""

from __future__ import annotations

import csv
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from google.api_core.exceptions import Conflict, PreconditionFailed

from lakehouse.config import Settings
from lakehouse.generation import load_dataset
from lakehouse.schema import FIELDS, validate_dataset

LOGGER = logging.getLogger(__name__)
CONTENT_TYPE = "text/csv"


class IngestionError(Exception):
    pass


class ReadError(IngestionError):
    pass


class ValidationError(IngestionError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


class ObjectAlreadyExistsError(IngestionError):
    def __init__(self, object_path: str) -> None:
        self.object_path = object_path
        super().__init__(f"objeto já existe: {object_path}")


class UploadError(IngestionError):
    pass


@dataclass(frozen=True)
class UploadResult:
    entity: str
    source_file: str
    object_path: str
    batch_id: str
    sha256: str
    row_count: int


@dataclass(frozen=True)
class BatchResult:
    bucket_name: str
    ingestion_date: date
    uploads: tuple[UploadResult, ...]


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_batch_id(entity: str, checksum_value: str) -> str:
    digest = hashlib.sha256(f"{entity}:{checksum_value}".encode("utf-8")).hexdigest()
    return f"{entity}-{digest[:16]}"


def build_object_path(entity: str, file_name: str, ingestion_date: date) -> str:
    return f"landing/{entity}/ingestion_date={ingestion_date.isoformat()}/{file_name}"


def _log(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    logger.log(level, event, extra=fields)


def _read_dataset(source_dir: Path) -> dict[str, list[dict[str, str]]]:
    try:
        dataset = load_dataset(source_dir)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ReadError(f"falha ao ler {source_dir}: {exc}") from exc
    return {entity: list(rows) for entity, rows in dataset.items()}


def ingest_directory(
    source_dir: Path,
    settings: Settings,
    *,
    client: Any | None = None,
    ingestion_date: date | None = None,
    now: datetime | None = None,
    logger: logging.Logger | None = None,
) -> BatchResult:
    if not settings.gcs_bucket_name:
        raise IngestionError("GCS_BUCKET_NAME não configurado")

    log = logger or LOGGER
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    batch_date = ingestion_date or current_time.date()

    _log(
        log,
        logging.INFO,
        "ingestion.started",
        pipeline_name=settings.pipeline_name,
        stage="ingestion",
        status="started",
        bucket_name=settings.gcs_bucket_name,
        source_dir=str(source_dir),
        ingestion_date=batch_date.isoformat(),
        file_count=len(FIELDS),
    )

    dataset = _read_dataset(source_dir)
    errors = validate_dataset(dataset)
    if errors:
        for error in errors:
            _log(
                log,
                logging.ERROR,
                "ingestion.validation_failed",
                pipeline_name=settings.pipeline_name,
                stage="ingestion",
                status="failure",
                source_dir=str(source_dir),
                ingestion_date=batch_date.isoformat(),
                error=error,
            )
        raise ValidationError(errors)

    storage_client = client
    if storage_client is None:
        from google.cloud import storage

        storage_client = storage.Client(project=settings.project_id)
    bucket = storage_client.bucket(settings.gcs_bucket_name)

    uploads: list[UploadResult] = []
    for entity in FIELDS:
        source_file = f"{entity}.csv"
        source_path = source_dir / source_file
        checksum_value = checksum(source_path)
        batch_id = build_batch_id(entity, checksum_value)
        object_path = build_object_path(entity, source_file, batch_date)
        metadata = {
            "batch_id": batch_id,
            "sha256": checksum_value,
            "source_file": object_path,
            "ingestion_date": batch_date.isoformat(),
            "ingested_at": current_time.isoformat().replace("+00:00", "Z"),
            "row_count": str(len(dataset[entity])),
        }

        blob = bucket.blob(object_path)
        blob.metadata = metadata
        try:
            blob.upload_from_filename(
                str(source_path),
                content_type=CONTENT_TYPE,
                if_generation_match=0,
            )
        except (PreconditionFailed, Conflict) as exc:
            _log(
                log,
                logging.ERROR,
                "ingestion.object_exists",
                pipeline_name=settings.pipeline_name,
                stage="ingestion",
                status="failure",
                batch_id=batch_id,
                entity=entity,
                source_file=source_file,
                object_path=object_path,
                sha256=checksum_value,
            )
            raise ObjectAlreadyExistsError(object_path) from exc
        except Exception as exc:
            _log(
                log,
                logging.ERROR,
                "ingestion.upload_failed",
                pipeline_name=settings.pipeline_name,
                stage="ingestion",
                status="failure",
                batch_id=batch_id,
                entity=entity,
                source_file=source_file,
                object_path=object_path,
                error=str(exc),
            )
            raise UploadError(f"falha no upload de {object_path}: {exc}") from exc

        row_count = len(dataset[entity])
        _log(
            log,
            logging.INFO,
            "ingestion.uploaded",
            pipeline_name=settings.pipeline_name,
            stage="ingestion",
            status="success",
            batch_id=batch_id,
            entity=entity,
            source_file=source_file,
            object_path=object_path,
            sha256=checksum_value,
            row_count=row_count,
        )
        uploads.append(
            UploadResult(
                entity=entity,
                source_file=source_file,
                object_path=object_path,
                batch_id=batch_id,
                sha256=checksum_value,
                row_count=row_count,
            )
        )

    _log(
        log,
        logging.INFO,
        "ingestion.completed",
        pipeline_name=settings.pipeline_name,
        stage="ingestion",
        status="success",
        bucket_name=settings.gcs_bucket_name,
        ingestion_date=batch_date.isoformat(),
        uploaded_count=len(uploads),
    )
    return BatchResult(
        bucket_name=settings.gcs_bucket_name,
        ingestion_date=batch_date,
        uploads=tuple(uploads),
    )


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    result = ingest_directory(Path("data/sample"), settings)
    for upload in result.uploads:
        print(upload.object_path)


if __name__ == "__main__":
    main()
