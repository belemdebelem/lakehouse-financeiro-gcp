"""Configurações mínimas do projeto (Fases 1, 4, 5 e 7)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    location: str
    gcs_bucket_name: str
    bq_dataset_bronze: str
    bq_dataset_silver: str
    bq_dataset_gold: str
    bq_dataset_ops: str
    pipeline_name: str
    log_level: str
    dbt_target: str = "dev"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            region=os.getenv("GCP_REGION", "southamerica-east1"),
            location=os.getenv("GCP_LOCATION", "southamerica-east1"),
            gcs_bucket_name=os.getenv("GCS_BUCKET_NAME", ""),
            bq_dataset_bronze=os.getenv("BQ_DATASET_BRONZE", "bronze"),
            bq_dataset_silver=os.getenv("BQ_DATASET_SILVER", "silver"),
            bq_dataset_gold=os.getenv("BQ_DATASET_GOLD", "gold"),
            bq_dataset_ops=os.getenv("BQ_DATASET_OPS", "ops"),
            pipeline_name=os.getenv("PIPELINE_NAME", "lakehouse-financeiro"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            dbt_target=os.getenv("DBT_TARGET", "dev"),
        )
