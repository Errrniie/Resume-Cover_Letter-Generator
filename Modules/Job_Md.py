#!/usr/bin/env python3
"""
Save a temporary job description + posting URL as Markdown under Job_MD/.

Only one active job_*.md is kept; each save deletes prior job_*.md files and increments
the sequence counter in Job_MD/.sequence.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Modules.Application_Path import project_root

JOB_MD_DIR_NAME = "Job_MD"
SEQUENCE_FILE_NAME = ".sequence"
JOB_MD_GLOB = "job_*.md"


@dataclass(frozen=True)
class JobMdSaveResult:
    """Outcome of writing a temporary job description file."""

    path: Path
    sequence: int


def job_md_root(*, base: Path | None = None) -> Path:
    return (base or project_root()) / JOB_MD_DIR_NAME


def _sequence_path(root: Path) -> Path:
    return root / SEQUENCE_FILE_NAME


def _read_next_sequence(root: Path) -> int:
    """Read .sequence and return the next value to use (starts at 1)."""
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


def _delete_existing_job_md_files(root: Path) -> None:
    for path in root.glob(JOB_MD_GLOB):
        if path.is_file():
            path.unlink()


def format_job_md_content(description: str, url: str) -> str:
    """Build GPT-friendly markdown for a job posting."""
    desc = description.strip()
    link = url.strip()
    return (
        "# Job posting\n\n"
        f"**URL:** {link}\n\n"
        "## Job description\n\n"
        f"{desc}\n"
    )


def _validate_inputs(description: str, url: str) -> tuple[str, str]:
    desc = description.strip()
    link = url.strip()
    if not desc:
        raise ValueError("Job description must be non-empty after trim")
    if not link:
        raise ValueError("Job posting URL must be non-empty after trim")
    return desc, link


def save_temporary_job_md(
    description: str,
    url: str,
    *,
    base: Path | None = None,
) -> JobMdSaveResult:
    """
    Replace any prior job_*.md in Job_MD/ with a new numbered file.

    Sequence in Job_MD/.sequence increases monotonically (job_001, job_002, …).
    """
    desc, link = _validate_inputs(description, url)
    root = job_md_root(base=base)
    root.mkdir(parents=True, exist_ok=True)

    _delete_existing_job_md_files(root)
    sequence = _read_next_sequence(root)

    filename = f"job_{sequence:03d}.md"
    path = (root / filename).resolve()
    path.write_text(format_job_md_content(desc, link), encoding="utf-8")

    return JobMdSaveResult(path=path, sequence=sequence)


def get_current_job_md_path(*, base: Path | None = None) -> Path | None:
    """Return the sole job_*.md file in Job_MD/, or None if none exist."""
    root = job_md_root(base=base)
    if not root.is_dir():
        return None

    matches = sorted(root.glob(JOB_MD_GLOB))
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        return None

    return max(matches, key=lambda p: p.name).resolve()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save a temporary job description Markdown file under Job_MD/.",
    )
    parser.add_argument("--url", required=True, help="Job posting URL.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--description",
        help="Job description text (inline).",
    )
    group.add_argument(
        "--description-file",
        type=Path,
        help="Path to a text file containing the job description.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.description_file is not None:
        try:
            description = args.description_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading description file: {exc}", file=sys.stderr)
            return 1
    else:
        description = args.description or ""

    try:
        result = save_temporary_job_md(description, args.url)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Saved: {result.path} (job_{result.sequence:03d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
