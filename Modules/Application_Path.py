#!/usr/bin/env python3
"""
Resolve (and create if needed) per-application folder paths.

Layout:
  Applications/{company}/{position}/
"""

from __future__ import annotations

import json
import re
from pathlib import Path

APPLICATIONS_DIR_NAME = "Applications"
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def project_root() -> Path:
    root = Path(__file__).resolve().parent
    return root.parent if root.name == "Modules" else root


def applications_root(base: Path | None = None) -> Path:
    return (base or project_root()) / APPLICATIONS_DIR_NAME


def sanitize_dir_name(text: str) -> str:
    cleaned = INVALID_PATH_CHARS.sub("", text.strip())
    return cleaned.rstrip(" .")


def _read_company_and_position(data: dict) -> tuple[str, str]:
    company = sanitize_dir_name(str(data.get("company", "")))
    position = sanitize_dir_name(str(data.get("position", "")))
    if not company:
        raise ValueError('JSON must include non-empty "company"')
    if not position:
        raise ValueError('JSON must include non-empty "position"')
    return company, position


def _find_existing_child(parent: Path, name: str) -> Path | None:
    if not parent.is_dir():
        return None
    target = name.casefold()
    for child in parent.iterdir():
        if child.is_dir() and child.name.casefold() == target:
            return child
    return None


def _ensure_child_dir(parent: Path, name: str) -> Path:
    existing = _find_existing_child(parent, name)
    if existing is not None:
        return existing
    path = parent / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_application_path(
    json_path: Path,
    *,
    applications_base: Path | None = None,
) -> Path:
    """
    Load company and position from JSON, ensure Applications/{company}/{position}/ exists,
    and return the position folder path.
    """
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    return resolve_application_path_from_data(data, applications_base=applications_base)


def resolve_application_path_from_data(
    data: dict,
    *,
    applications_base: Path | None = None,
) -> Path:
    company, position = _read_company_and_position(data)
    apps_root = applications_root(applications_base)
    apps_root.mkdir(parents=True, exist_ok=True)

    company_dir = _ensure_child_dir(apps_root, company)
    return _ensure_child_dir(company_dir, position)
