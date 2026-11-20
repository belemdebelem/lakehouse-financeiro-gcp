import json
import logging

from lakehouse.observability import CloudLoggingHandler, JsonFormatter


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse()


def test_json_formatter_preserves_structured_fields():
    record = logging.makeLogRecord(
        {
            "name": "test",
            "levelno": logging.ERROR,
            "msg": "pipeline.failed",
            "args": (),
            "pipeline_name": "lakehouse-financeiro",
            "batch_id": "batch-123",
            "status": "failure",
        }
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "pipeline.failed"
    assert payload["pipeline_name"] == "lakehouse-financeiro"
    assert payload["batch_id"] == "batch-123"
    assert payload["severity"] == "ERROR"


def test_cloud_logging_handler_writes_structured_log_entry():
    session = FakeSession()
    handler = CloudLoggingHandler("project-123", session=session)
    record = logging.makeLogRecord(
        {
            "name": "test",
            "levelno": logging.ERROR,
            "msg": "pipeline.failed",
            "args": (),
            "pipeline_name": "lakehouse-financeiro",
            "batch_id": "batch-123",
            "status": "failure",
        }
    )

    handler.emit(record)

    url, body, timeout = session.calls[0]
    entry = body["entries"][0]
    assert url.endswith("/entries:write")
    assert timeout == 5
    assert entry["logName"] == (
        "projects/project-123/logs/lakehouse-financeiro-pipeline"
    )
    assert entry["jsonPayload"]["batch_id"] == "batch-123"
    assert entry["jsonPayload"]["status"] == "failure"
    assert entry["severity"] == "ERROR"
