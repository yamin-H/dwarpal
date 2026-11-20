import json
import logging
import re
import sys

import pytest

from app.observability.logging import JsonFormatter, RequestIdFilter, configure_logging

URL = "/v1/chat/completions"
BODY = {"model": "auto", "messages": [{"role": "user", "content": "hello world"}]}


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.addFilter(RequestIdFilter())
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def logs():
    logger = logging.getLogger("dwarpal")
    handler = Capture()
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


def request_lines(logs, path=None):
    return [r for r in logs.records
            if r.getMessage() == "request" and (path is None or r.path == path)]


def test_response_has_a_generated_request_id(client):
    r = client.get("/healthz")
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])


def test_valid_incoming_request_id_is_kept(client):
    r = client.get("/healthz", headers={"X-Request-ID": "kong-abc_123"})
    assert r.headers["x-request-id"] == "kong-abc_123"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "a;b", "<script>"])
def test_unsafe_incoming_ids_are_replaced(client, bad):
    assert client.get("/healthz", headers={"X-Request-ID": bad}).headers["x-request-id"] != bad


def test_request_log_has_context_and_no_secrets(client, auth, logs):
    r = client.post(URL, json=BODY, headers=auth)
    entries = request_lines(logs, URL)
    assert len(entries) == 1
    rec = entries[0]
    assert (rec.request_id, rec.status, rec.method) == (r.headers["x-request-id"], 200, "POST")
    assert rec.tenant == "demo-app" and rec.cache == "DISABLED"
    dumped = "\n".join(JsonFormatter().format(x) for x in logs.records)
    assert auth["Authorization"].split()[1] not in dumped
    assert "hello world" not in dumped


def test_health_checks_are_not_logged_at_info(client, logs):
    client.get("/healthz")
    assert not request_lines(logs)


def test_request_id_is_attached_to_other_log_lines(client, auth, logs, monkeypatch):
    def boom(**kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(client.app.state.store, "record_usage", boom)
    r = client.post(URL, json=BODY, headers=auth)
    lines = [x for x in logs.records if x.getMessage() == "usage logging failed"]
    assert lines and lines[0].request_id == r.headers["x-request-id"]


def make_record(**extra):
    rec = logging.LogRecord("dwarpal", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


def test_json_formatter_outputs_valid_json_with_extras():
    data = json.loads(JsonFormatter().format(make_record(tenant="demo-app", duration_ms=12,
                                                          request_id="abc")))
    assert data["message"] == "hello world" and data["level"] == "INFO"
    assert data["tenant"] == "demo-app" and data["duration_ms"] == 12
    assert data["request_id"] == "abc" and "ts" in data


def test_non_ascii_survives():
    rec = make_record()
    rec.msg, rec.args = "যাকাত", ()
    assert "যাকাত" in JsonFormatter().format(rec)


def exc_record():
    try:
        raise ValueError("secret-sk-123")
    except ValueError:
        return logging.LogRecord("dwarpal", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())


def test_tracebacks_are_omitted_by_default():
    data = json.loads(JsonFormatter().format(exc_record()))
    assert data["exc_type"] == "ValueError" and "traceback" not in data
    assert "secret-sk-123" not in json.dumps(data)


def test_tracebacks_can_be_enabled():
    data = json.loads(JsonFormatter(tracebacks=True).format(exc_record()))
    assert "ValueError" in data["traceback"]


def test_configure_logging_is_idempotent():
    configure_logging("INFO", True, False)
    configure_logging("INFO", True, False)
    ours = [h for h in logging.getLogger("dwarpal").handlers if getattr(h, "_dwarpal", False)]
    assert len(ours) == 1