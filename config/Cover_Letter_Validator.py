"""Validate cover letter JSON required fields."""

from __future__ import annotations

import json
from pathlib import Path

from config.Cover_Letter_Config import REQUIRED_COVER_LETTER_FIELDS
from config.Issues import ValidationIssue, ValidationResult

_MISSING = "required but missing"
_EMPTY = "required but missing or empty"


def _field_text(raw: dict, field: str) -> str:
    value = raw.get(field)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def validate_cover_letter_data(raw: dict) -> ValidationResult:
    """Ensure all required cover letter fields are present and non-empty after trim."""
    if not isinstance(raw, dict):
        return ValidationResult(
            valid=False,
            issues=[ValidationIssue("json", "root must be a JSON object")],
        )

    issues: list[ValidationIssue] = []

    for field in REQUIRED_COVER_LETTER_FIELDS:
        if field not in raw:
            issues.append(ValidationIssue(field, _MISSING))
            continue
        if not _field_text(raw, field):
            issues.append(ValidationIssue(field, _EMPTY))

    return ValidationResult(valid=len(issues) == 0, issues=issues)


def validate_cover_letter_json_file(json_path: Path) -> ValidationResult:
    """Load a cover letter JSON file and validate required fields."""
    if not json_path.is_file():
        return ValidationResult(
            valid=False,
            issues=[ValidationIssue("file", f"not found: {json_path}")],
        )

    try:
        with json_path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        return ValidationResult(
            valid=False,
            issues=[ValidationIssue("json", f"invalid JSON: {exc}")],
        )

    return validate_cover_letter_data(raw)
