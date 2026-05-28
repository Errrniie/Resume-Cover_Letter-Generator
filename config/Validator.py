"""Validate resume JSON data against config bullet limits."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from config.Issues import ValidationIssue, ValidationResult  # re-exported
from config.Loader import Config, load_config
from config.Metadata_Validator import validate_metadata

__all__ = [
    "ValidationIssue",
    "ValidationResult",
    "validate_data",
    "validate_json_file",
    "validate_metadata",
    "validate_resume_json",
]

BULLETS_ARRAY_SUFFIX = "_bullets"
FLAT_BULLET_KEY_RE = re.compile(r"^(\w+)_bullet_(\d+)$")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_text(value: object) -> str:
    if _blank(value):
        return ""
    return str(value).strip()


def extract_bullet_groups(raw: dict) -> dict[str, list[str]]:
    """
    Collect bullets the same way Fill_Resume.py does:
    - arrays: goose_bullets, peizo_bullets, ...
    - flat keys: goose_bullet_1, goose_bullet_2, ...
    """
    groups: dict[str, list[str]] = {}
    flat: dict[str, dict[int, str]] = {}

    for key, value in raw.items():
        if key == "skills" or not isinstance(key, str):
            continue
        if key.endswith(BULLETS_ARRAY_SUFFIX):
            if not isinstance(value, list):
                raise ValueError(f'"{key}" must be an array of strings')
            prefix = key[: -len(BULLETS_ARRAY_SUFFIX)]
            groups[prefix] = [_as_text(item) for item in value if not _blank(item)]
            continue

        match = FLAT_BULLET_KEY_RE.match(key)
        if match:
            prefix, index = match.group(1), int(match.group(2))
            text = _as_text(value)
            if text:
                flat.setdefault(prefix, {})[index] = text

    for prefix, indices in flat.items():
        if prefix not in groups:
            groups[prefix] = [indices[i] for i in sorted(indices)]

    return groups


def validate_data(raw: dict, config: Config) -> ValidationResult:
    """Check bullet groups in parsed JSON against configured limits."""
    issues: list[ValidationIssue] = []

    try:
        groups = extract_bullet_groups(raw)
    except ValueError as exc:
        return ValidationResult(valid=False, issues=[ValidationIssue("json", str(exc))])

    for prefix, bullets in sorted(groups.items()):
        limits = config.limits_for_group(prefix)

        if len(bullets) > limits.max_count:
            issues.append(
                ValidationIssue(
                    f"{prefix}{BULLETS_ARRAY_SUFFIX}",
                    f"{len(bullets)} bullets (max {limits.max_count})",
                )
            )

        for index, text in enumerate(bullets, start=1):
            length = len(text)
            if length > limits.max_characters:
                issues.append(
                    ValidationIssue(
                        f"{prefix}{BULLETS_ARRAY_SUFFIX}[{index}]",
                        f"{length} characters (max {limits.max_characters})",
                    )
                )

    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
        bullet_groups=groups,
    )


def validate_resume_json(raw: dict, config: Config) -> ValidationResult:
    """Run metadata validation, then bullet validation; return combined issues."""
    meta = validate_metadata(raw)
    bullet = validate_data(raw, config)
    issues = meta.issues + bullet.issues
    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
        bullet_groups=bullet.bullet_groups,
    )


def validate_json_file(
    json_path: Path,
    config: Config | None = None,
) -> ValidationResult:
    """Load a JSON file and validate its bullet content."""
    cfg = config or load_config()

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

    if not isinstance(raw, dict):
        return ValidationResult(
            valid=False,
            issues=[ValidationIssue("json", "root must be a JSON object")],
        )

    return validate_resume_json(raw, cfg)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate resume JSON bullet lengths against config/settings.json.",
    )
    parser.add_argument("json", type=Path, help="Path to resume data JSON file.")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to settings.json (default: config/settings.json).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    result = validate_json_file(args.json, config)
    if result.valid:
        print(f"OK: {args.json} passes metadata and bullet validation.")
        return 0

    print(f"Validation failed: {args.json}", file=sys.stderr)
    for message in result.messages():
        print(f"  - {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
