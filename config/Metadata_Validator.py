"""Validate required application metadata fields in resume JSON."""

from __future__ import annotations

from config.Issues import ValidationIssue, ValidationResult

# Future: load from settings.json validation.required_fields per resume type.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = ("company", "position")

_MISSING = "required but missing"
_EMPTY = "required but missing or empty"


def _field_text(raw: dict, field: str) -> str:
    value = raw.get(field)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def validate_metadata(raw: dict) -> ValidationResult:
    """Ensure company and position are present and non-empty after trim."""
    issues: list[ValidationIssue] = []

    for field in REQUIRED_METADATA_FIELDS:
        if field not in raw:
            issues.append(ValidationIssue(field, _MISSING))
            continue
        if not _field_text(raw, field):
            issues.append(ValidationIssue(field, _EMPTY))

    return ValidationResult(valid=len(issues) == 0, issues=issues)
