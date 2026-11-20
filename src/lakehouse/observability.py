"""Logs estruturados locais e envio opcional ao Cloud Logging."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

LOG_NAME = "lakehouse-financeiro-pipeline"
LOGGING_SCOPE = "https://www.googleapis.com/auth/logging.write"
LOGGING_URL = "https://logging.googleapis.com/v2/entries:write"
_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = _record_payload(record)
        payload["severity"] = _severity(record.levelno)
        payload["timestamp"] = datetime.fromtimestamp(record.created, timezone.utc).isoformat()
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


class CloudLoggingHandler(logging.Handler):
    """Envia cada registro ao endpoint oficial usando ADC e logging.write."""

    def __init__(self, project_id: str, *, session: Any | None = None) -> None:
        super().__init__()
        if session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, detected_project = google.auth.default(scopes=[LOGGING_SCOPE])
            project_id = project_id or detected_project or ""
            session = AuthorizedSession(credentials)
        if not project_id:
            raise ValueError("GCP_PROJECT_ID ausente para Cloud Logging")
        self.project_id = project_id
        self.session = session

    def emit(self, record: logging.LogRecord) -> None:
        payload = _record_payload(record)
        entry: dict[str, object] = {
            "logName": f"projects/{self.project_id}/logs/{LOG_NAME}",
            "resource": {
                "type": "global",
                "labels": {"project_id": self.project_id},
            },
            "severity": _severity(record.levelno),
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "jsonPayload": payload,
        }
        if record.exc_info:
            entry["jsonPayload"]["exception"] = logging.Formatter().formatException(
                record.exc_info
            )
        try:
            response = self.session.post(
                LOGGING_URL,
                json={"entries": [entry], "partialSuccess": True},
                timeout=5,
            )
            response.raise_for_status()
        except Exception:
            self.handleError(record)


def _record_payload(record: logging.LogRecord) -> dict[str, object]:
    payload: dict[str, object] = {"message": record.getMessage()}
    payload.update(
        {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_FIELDS and not key.startswith("_")
        }
    )
    return payload


def _severity(levelno: int) -> str:
    if levelno >= logging.CRITICAL:
        return "CRITICAL"
    if levelno >= logging.ERROR:
        return "ERROR"
    if levelno >= logging.WARNING:
        return "WARNING"
    if levelno >= logging.INFO:
        return "INFO"
    return "DEBUG"


def configure_logging(
    *, level: str = "INFO", project_id: str = "", cloud_enabled: bool = False
) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(JsonFormatter())
        root.addHandler(stream)
    if cloud_enabled and not any(isinstance(h, CloudLoggingHandler) for h in root.handlers):
        root.addHandler(CloudLoggingHandler(project_id))
