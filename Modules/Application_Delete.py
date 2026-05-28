#!/usr/bin/env python3
"""
Safe delete helpers for generated files under Applications/.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Modules.Application_Path import applications_root

ALLOWED_SUFFIXES = frozenset({".docx", ".pdf"})


@dataclass(frozen=True)
class DeleteResult:
    """Outcome of deleting application output file(s) or a position folder."""

    deleted: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_under_root(path: Path, root: Path) -> bool:
    root = root.resolve()
    path = path.resolve()
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_deletable_application_path(path: Path, *, base: Path | None = None) -> bool:
    """True if resolved path is a file under Applications/ with a .docx or .pdf suffix."""
    try:
        _validate_deletable_file(path, base=base)
    except ValueError:
        return False
    return path.resolve().is_file()


def _validate_deletable_file(path: Path, *, base: Path | None = None) -> Path:
    """Resolve path and ensure it is an allowed application output file."""
    apps = applications_root(base).resolve()
    resolved = Path(path).resolve()

    if not _is_under_root(resolved, apps):
        raise ValueError(f"Path is not under Applications/: {resolved}")

    if resolved == apps:
        raise ValueError("Cannot delete the Applications root")

    suffix = resolved.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(
            f"Only .docx and .pdf files can be deleted, got: {resolved.name}"
        )

    return resolved


def paired_output_paths(docx_or_pdf: Path) -> list[Path]:
    """If input is .docx, include sibling .pdf with same stem; vice versa."""
    path = Path(docx_or_pdf)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return [path, path.with_suffix(".pdf")]
    if suffix == ".pdf":
        return [path, path.with_suffix(".docx")]
    return [path]


def delete_application_file(
    path: Path,
    *,
    include_paired_pdf_docx: bool = False,
    base: Path | None = None,
) -> DeleteResult:
    """
    Delete one application output file (and optionally its paired .docx/.pdf).

    Raises:
        ValueError: Path outside Applications/, wrong type, or not a file.
        FileNotFoundError: Primary path does not exist.
    """
    primary = _validate_deletable_file(path, base=base)

    if not primary.is_file():
        if primary.exists():
            raise ValueError(f"Path is not a file: {primary}")
        raise FileNotFoundError(f"File not found: {primary}")

    targets = [primary]
    if include_paired_pdf_docx:
        seen = {primary}
        for candidate in paired_output_paths(primary):
            resolved = _validate_deletable_file(candidate, base=base)
            if resolved not in seen:
                targets.append(resolved)
                seen.add(resolved)

    deleted: list[Path] = []
    skipped: list[Path] = []
    errors: list[str] = []

    for target in targets:
        if not target.is_file():
            if target == primary:
                raise FileNotFoundError(f"File not found: {target}")
            skipped.append(target)
            continue
        try:
            target.unlink()
            deleted.append(target)
        except OSError as exc:
            errors.append(f"{target}: {exc}")

    return DeleteResult(deleted=deleted, skipped=skipped, errors=errors)


def _validate_position_folder(path: Path, *, base: Path | None = None) -> Path:
    apps = applications_root(base).resolve()
    resolved = Path(path).resolve()

    if not _is_under_root(resolved, apps):
        raise ValueError(f"Path is not under Applications/: {resolved}")

    if resolved == apps:
        raise ValueError("Cannot delete the Applications root")

    try:
        relative = resolved.relative_to(apps)
    except ValueError as exc:
        raise ValueError(f"Path is not under Applications/: {resolved}") from exc

    if len(relative.parts) != 2:
        raise ValueError(
            "Must be a position folder: Applications/{company}/{position}/"
        )

    if not resolved.is_dir():
        if not resolved.exists():
            raise FileNotFoundError(f"Folder not found: {resolved}")
        raise ValueError(f"Path is not a directory: {resolved}")

    return resolved


def delete_position_folder(
    position_dir: Path,
    *,
    base: Path | None = None,
) -> DeleteResult:
    """
    Delete entire Applications/{company}/{position}/ and its contents.

    Does not delete company-only folders or the Applications root.
  """
    folder = _validate_position_folder(position_dir, base=base)

    deleted: list[Path] = []
    errors: list[str] = []

    for file_path in sorted(folder.rglob("*")):
        if file_path.is_file():
            deleted.append(file_path.resolve())

    try:
        shutil.rmtree(folder)
    except OSError as exc:
        errors.append(f"{folder}: {exc}")

    return DeleteResult(deleted=deleted, skipped=[], errors=errors)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete application output files under Applications/.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to a .docx or .pdf under Applications/.",
    )
    parser.add_argument(
        "--pair",
        action="store_true",
        help="Also delete the paired .docx/.pdf with the same stem.",
    )
    parser.add_argument(
        "--position-folder",
        action="store_true",
        help="Delete entire Applications/{company}/{position}/ folder.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        if args.position_folder:
            result = delete_position_folder(args.path)
        else:
            result = delete_application_file(
                args.path,
                include_paired_pdf_docx=args.pair,
            )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for path in result.deleted:
        print(f"Deleted: {path}")
    for path in result.skipped:
        print(f"Skipped (not found): {path}")
    for message in result.errors:
        print(f"Warning: {message}", file=sys.stderr)

    if not result.deleted and not result.skipped and not result.errors:
        print("Nothing to delete.")
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
