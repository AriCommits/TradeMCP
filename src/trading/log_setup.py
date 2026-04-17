import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """
    Structured, machine-readable JSON log format.
    No print statements should be used in the agent logic.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include any extra attributes passed via the `extra` dict
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data) # type: ignore
            
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)

def setup_logging(level: int = logging.INFO, stream=None):
    """
    Log Levels Mapping:
    - DEBUG: internal agent reasoning, intermediate steps.
    - INFO: research findings, execution decisions, order placements.
    - WARNING: unexpected states, partial fills, high slippage detected.
    - ERROR: API failures, order rejections, unhandled exceptions.
    - CRITICAL: kill switch triggered, data integrity violation, auth failure.
    """
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    if stream is None:
        stream = sys.stdout

    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    return logger

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
