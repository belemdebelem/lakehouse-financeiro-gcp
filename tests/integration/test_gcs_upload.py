import os
from datetime import date
from pathlib import Path

import pytest

from lakehouse.config import Settings
from lakehouse.ingestion import ObjectAlreadyExistsError, ingest_directory

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_GCS_INTEGRATION") != "1",
    reason="integração com GCS é opt-in via RUN_GCS_INTEGRATION=1",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
INGESTION_DATE = date(2026, 11, 17)


def test_gcs_upload_is_idempotent():
    settings = Settings.from_env()
    if not settings.gcs_bucket_name:
        pytest.skip("GCS_BUCKET_NAME não configurado")

    try:
        result = ingest_directory(
            SAMPLE_DIR,
            settings,
            ingestion_date=INGESTION_DATE,
        )
    except ObjectAlreadyExistsError:
        return

    assert len(result.uploads) == 3
    assert {upload.entity for upload in result.uploads} == {
        "customers",
        "contracts",
        "installments",
    }

    with pytest.raises(ObjectAlreadyExistsError):
        ingest_directory(
            SAMPLE_DIR,
            settings,
            ingestion_date=INGESTION_DATE,
        )
