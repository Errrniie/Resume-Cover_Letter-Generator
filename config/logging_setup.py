"""Configure file logging for a single pipeline run."""

from __future__ import annotations

import logging
from pathlib import Path

PIPELINE_LOGGER_ROOT = "resume"


def configure_run_logging(
    log_path: Path,
    *,
    document_type: str = "resume",
) -> logging.Logger:
    """
    Attach a dated FileHandler for this run. Clears prior handlers on the resume logger tree.

    document_type is reserved for future cover-letter runs (same Logs/{company}/ tree).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger(PIPELINE_LOGGER_ROOT)
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    root.propagate = False

    handler = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    logger = logging.getLogger(f"{PIPELINE_LOGGER_ROOT}.{document_type}")
    logger.info("Logging to %s (document_type=%s)", log_path, document_type)
    return logger


def shutdown_run_logging() -> None:
    """Remove handlers so the next run does not duplicate log lines."""
    root = logging.getLogger(PIPELINE_LOGGER_ROOT)
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)
