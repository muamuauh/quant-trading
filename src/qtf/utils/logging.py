"""Structured JSON logging to stdout and to logs/qtf.jsonl."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from qtf.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = getattr(record, "extras", None)
        if extras:
            payload.update(extras)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)
    if _configured:
        return logger

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_path: Path = settings.log_dir / "qtf.jsonl"

    handler_stream = logging.StreamHandler(sys.stdout)
    handler_stream.setFormatter(JsonFormatter())

    handler_file = logging.FileHandler(log_path, encoding="utf-8")
    handler_file.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler_stream)
    root.addHandler(handler_file)
    root.setLevel(logging.INFO)

    _configured = True
    return logger


def log_event(logger: logging.Logger, msg: str, **extras: Any) -> None:
    """Emit an INFO log with structured extras."""
    logger.info(msg, extra={"extras": extras})
