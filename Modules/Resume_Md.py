#!/usr/bin/env python3
"""
Save a temporary resume JSON snapshot as Markdown under Resume_MD/.

Only one active resume_*.md is kept; each save deletes prior resume_*.md files and increments
the sequence counter in Resume_MD/.sequence.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Modules.Application_Path import project_root
from Modules.Fill_Resume import parse_resume_data
from config.Validator import extract_bullet_groups


def _as_text(value: object) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    return str(value).strip()

RESUME_MD_DIR_NAME = "Resume_MD"
SEQUENCE_FILE_NAME = ".sequence"
RESUME_MD_GLOB = "resume_*.md"

EDUCATION_LINES = (
    "BS Aerospace Engineering, Illinois Institute of Technology (May 2027)",
    "BA Engineering Science, Benedictine University (May 2027)",
)

PROJECT_SECTIONS: tuple[tuple[str, str], ...] = (
    ("goose", "### Goose Deterrent System"),
    ("peizo", "### AFC Piezo-Actuator"),
    ("windturbine", "### Wind Turbine Revitalization"),
)

WORK_SECTIONS: tuple[tuple[str, str], ...] = (
    ("mostardi", "### Mostardi Platt - Air Emissions Engineer"),
    ("greenway", "### GreenWay Landscaping - Operations Lead"),
)


@dataclass(frozen=True)
class ResumeMdSaveResult:
    """Outcome of writing a temporary resume snapshot file."""

    path: Path
    sequence: int


def resume_md_root(*, base: Path | None = None) -> Path:
    return (base or project_root()) / RESUME_MD_DIR_NAME


def _sequence_path(root: Path) -> Path:
    return root / SEQUENCE_FILE_NAME


def _read_next_sequence(root: Path) -> int:
    path = _sequence_path(root)
    if path.is_file():
        raw = path.read_text(encoding="utf-8").strip()
        try:
            current = int(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid {path.name} contents: {raw!r}") from exc
        if current < 0:
            raise ValueError(f"Invalid {path.name}: must be a non-negative integer")
        next_value = current + 1
    else:
        next_value = 1

    path.write_text(f"{next_value}\n", encoding="utf-8")
    return next_value


def _delete_existing_resume_md_files(root: Path) -> None:
    for path in root.glob(RESUME_MD_GLOB):
        if path.is_file():
            path.unlink()


def _display_field(raw: dict, key: str) -> str:
    value = _as_text(raw.get(key, ""))
    return value if value else "Unknown"


def _primary_focus_block(raw: dict) -> list[str]:
    focus = _as_text(raw.get("primary_focus", ""))
    if not focus:
        return []
    return ["## Primary Focus", "", focus, ""]


def _bullet_section_blocks(
    groups: dict[str, list[str]],
    sections: tuple[tuple[str, str], ...],
) -> list[str]:
    lines: list[str] = []
    for prefix, heading in sections:
        bullets = groups.get(prefix, [])
        if not bullets:
            continue
        lines.append(heading)
        lines.append("")
        lines.extend(f"- {text}" for text in bullets)
        lines.append("")
    return lines


def _skills_block(raw: dict) -> list[str]:
    skills_raw = raw.get("skills")
    if not isinstance(skills_raw, list) or not skills_raw:
        return []

    try:
        categories = parse_resume_data(raw).skill_categories
    except ValueError:
        return []

    if not categories:
        return []

    lines = ["## Skills Emphasized", ""]
    for entry in categories:
        category = str(entry.get("category", "")).strip()
        skills = entry.get("skills", [])
        if not isinstance(skills, list):
            continue
        skill_names = [str(s).strip() for s in skills if str(s).strip()]
        if not category and not skill_names:
            continue
        if category:
            lines.append(f"**{category}**")
        if skill_names:
            lines.append(", ".join(skill_names))
        lines.append("")

    if lines == ["## Skills Emphasized", ""]:
        return []
    return lines


def format_resume_md_content(raw: dict) -> str:
    """Build GPT-friendly markdown from validated resume JSON."""
    company = _display_field(raw, "company")
    position = _display_field(raw, "position")
    groups = extract_bullet_groups(raw)

    parts: list[str] = [
        f"# Resume: {company} - {position}",
        "",
        *_primary_focus_block(raw),
        "## Education",
        "",
        *EDUCATION_LINES,
        "",
    ]

    project_lines = _bullet_section_blocks(groups, PROJECT_SECTIONS)
    if project_lines:
        parts.extend(["## Projects Highlighted", "", *project_lines])

    work_lines = _bullet_section_blocks(groups, WORK_SECTIONS)
    if work_lines:
        parts.extend(["## Work Experience Highlighted", "", *work_lines])

    parts.extend(_skills_block(raw))

    while parts and parts[-1] == "":
        parts.pop()

    return "\n".join(parts) + "\n"


def save_temporary_resume_md(
    raw: dict,
    *,
    base: Path | None = None,
) -> ResumeMdSaveResult:
    """
    Format and write Resume_MD/resume_NNN.md; delete prior resume_*.md first.

    Does not validate JSON — caller must validate first.
    """
    root = resume_md_root(base=base)
    root.mkdir(parents=True, exist_ok=True)

    _delete_existing_resume_md_files(root)
    sequence = _read_next_sequence(root)

    filename = f"resume_{sequence:03d}.md"
    path = (root / filename).resolve()
    path.write_text(format_resume_md_content(raw), encoding="utf-8")

    return ResumeMdSaveResult(path=path, sequence=sequence)


def get_current_resume_md_path(*, base: Path | None = None) -> Path | None:
    """Return the sole resume_*.md file in Resume_MD/, or None if none exist."""
    root = resume_md_root(base=base)
    if not root.is_dir():
        return None

    matches = sorted(root.glob(RESUME_MD_GLOB))
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        return None

    return max(matches, key=lambda p: p.name).resolve()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save a temporary resume Markdown snapshot under Resume_MD/.",
    )
    parser.add_argument("json", type=Path, help="Path to resume JSON data.")
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
        with args.json.open(encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error loading JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(raw, dict):
        print("Error: JSON root must be an object", file=sys.stderr)
        return 1

    from config.Loader import load_config
    from config.Metadata_Validator import validate_metadata
    from config.Validator import validate_data

    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    meta = validate_metadata(raw)
    if not meta.valid:
        print(f"Validation failed: {args.json}", file=sys.stderr)
        for message in meta.messages():
            print(f"  - {message}", file=sys.stderr)
        return 1

    bullets = validate_data(raw, cfg)
    if not bullets.valid:
        print(f"Validation failed: {args.json}", file=sys.stderr)
        for message in bullets.messages():
            print(f"  - {message}", file=sys.stderr)
        return 1

    try:
        result = save_temporary_resume_md(raw)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Saved: {result.path} (resume_{result.sequence:03d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
