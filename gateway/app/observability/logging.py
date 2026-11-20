import contextvars
import json
import logging
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message", "asctime", "request_id",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, tracebacks: bool = False) -> None:
        super().__init__()
        self.tracebacks = tracebacks

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__
            if self.tracebacks:
                payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", json_logs: bool = True, tracebacks: bool = False) -> None:
    logger = logging.getLogger("dwarpal")
    for handler in list(logger.handlers):
        if getattr(handler, "_dwarpal", False):  # idempotent: create_app runs once per test
            logger.removeHandler(handler)
    handler = logging.StreamHandler()
    handler._dwarpal = True
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter(tracebacks)
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False