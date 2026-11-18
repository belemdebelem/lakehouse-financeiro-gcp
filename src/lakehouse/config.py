"""Configurações mínimas do projeto (Fase 1)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    location: str
    pipeline_name: str
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            region=os.getenv("GCP_REGION", "southamerica-east1"),
            location=os.getenv("GCP_LOCATION", "southamerica-east1"),
            pipeline_name=os.getenv("PIPELINE_NAME", "lakehouse-financeiro"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
