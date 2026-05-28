"""Resolve dated log file paths under Logs/{company}/."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from Modules.Application_Path import project_root, sanitize_dir_name

LOGS_DIR_NAME = "Logs"

_DOCUMENT_PREFIX = {
    "resume": "Resume",
    "cover_letter": "CoverLetter",
}


def logs_root(base: Path | None = None) -> Path:
    return (base or project_root()) / LOGS_DIR_NAME


def ensure_logs_company_dir(company: str, *, base: Path | None = None) -> Path:
    """Create Logs/{company}/ if needed (mirrors Applications company folders)."""
    name = sanitize_dir_name(company)
    path = logs_root(base) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _filename_part(text: str) -> str:
    """Same rules as Main.sanitize_filename_part (lazy import avoids cycles)."""
    from Main import sanitize_filename_part

    return sanitize_filename_part(text)


def resolve_log_file_path(
    raw: dict,
    *,
    document_type: str = "resume",
    run_date: date | None = None,
    base: Path | None = None,
) -> Path:
    """
    Logs/{company}/Resume_{Company}_{Position}_{YYYY-MM-DD}.log

    Uses position for the position segment. Falls back to _unknown when metadata is incomplete
    (e.g. logging a failed metadata check).
    """
    prefix = _DOCUMENT_PREFIX.get(document_type, document_type.title())
    company_raw = str(raw.get("company", "")).strip()
    position_raw = str(raw.get("position", "")).strip()
    company_dir_name = sanitize_dir_name(company_raw) if company_raw else "_unknown"
    company_file = _filename_part(company_raw) or "_unknown"
    position_file = _filename_part(position_raw) or "_unknown"
    day = (run_date or date.today()).isoformat()

    company_dir = ensure_logs_company_dir(company_dir_name, base=base)
    filename = f"{prefix}_{company_file}_{position_file}_{day}.log"
    return company_dir / filename
