#!/usr/bin/env python3
"""
Convert filled resume .docx outputs to PDF.

Use after Fill_Resume.py creates a document in Test_Docs/ (e.g. Ernesto_Carlton_Resume_Company_Position.docx).
Requires Microsoft Word on Windows (via docx2pdf).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_OUTPUT_DIR = "Test_Docs"
RESUME_DOCX_PATTERN = re.compile(
    r"^Ernesto_Carlton_Resume_.+\.docx$", re.IGNORECASE
)


def project_root() -> Path:
    root = Path(__file__).resolve().parent
    return root.parent if root.name == "Modules" else root


def resolve_path(path: Path, base: Path) -> Path:
    return path if path.is_absolute() else base / path


def pdf_path_for_docx(docx_path: Path) -> Path:
    return docx_path.with_suffix(".pdf")


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path | None = None) -> Path:
    """
    Convert a .docx file to PDF.

    Returns the path to the created PDF file.
    """
    docx_path = docx_path.resolve()
    if not docx_path.is_file():
        raise FileNotFoundError(f"Document not found: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx file, got: {docx_path.name}")

    out_pdf = (pdf_path or pdf_path_for_docx(docx_path)).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        from docx2pdf import convert
    except ImportError as exc:
        raise RuntimeError(
            "docx2pdf is not installed. Run: pip install docx2pdf"
        ) from exc

    com_initialized = False
    try:
        import pythoncom

        pythoncom.CoInitialize()
        com_initialized = True
    except ImportError:
        pass

    try:
        convert(str(docx_path), str(out_pdf))
    finally:
        if com_initialized:
            import pythoncom

            pythoncom.CoUninitialize()

    if not out_pdf.is_file():
        raise RuntimeError(f"PDF was not created: {out_pdf}")

    return out_pdf


def latest_resume_docx(output_dir: Path) -> Path | None:
    """Newest Ernesto_Carlton_Resume_*.docx in output_dir by modification time."""
    matches = [
        path
        for path in output_dir.glob("Ernesto_Carlton_Resume_*.docx")
        if RESUME_DOCX_PATTERN.match(path.name)
    ]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a filled resume .docx to PDF."
    )
    parser.add_argument(
        "docx",
        nargs="?",
        type=Path,
        help="Path to .docx file (default: newest Ernesto_Carlton_Resume_*.docx in Test_Docs/).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output PDF path (default: same name as .docx with .pdf extension).",
    )
    parser.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help=f"Directory to search for latest resume docx (default: {DEFAULT_OUTPUT_DIR}/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = project_root()

    if args.docx is not None:
        docx_path = resolve_path(args.docx, root)
    else:
        out_dir = resolve_path(args.output_dir, root)
        if not out_dir.is_dir():
            print(f"Error: Output directory not found: {out_dir}", file=sys.stderr)
            return 1
        docx_path = latest_resume_docx(out_dir)
        if docx_path is None:
            print(
                f"Error: No Ernesto_Carlton_Resume_*.docx files in {out_dir}. "
                "Run Fill_Resume.py first or pass a .docx path.",
                file=sys.stderr,
            )
            return 1

    pdf_out = resolve_path(args.output, root) if args.output else None

    try:
        pdf_path = convert_docx_to_pdf(docx_path, pdf_out)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Created: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
