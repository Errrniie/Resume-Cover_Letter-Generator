"""Check generated .docx files against configured page limits."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from config.Issues import ValidationIssue
from config.Loader import Config, load_config

KNOWN_DOCUMENT_TYPES = ("resume", "cover_letter")


@dataclass
class PageCheckResult:
    """Outcome of checking a generated document's page count."""

    within_limit: bool
    page_count: int | None
    max_pages: int
    document_type: str
    docx_path: Path
    skipped: bool = False
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.within_limit and not any(issue for issue in self.issues if not issue.warning)

    def warning_messages(self) -> list[str]:
        return [issue.format() for issue in self.issues if issue.warning]

    def error_messages(self) -> list[str]:
        return [issue.format() for issue in self.issues if not issue.warning]

    @property
    def over_page_limit(self) -> bool:
        """True when the document exceeds the configured page limit."""
        if self.skipped or self.page_count is None:
            return False
        return self.page_count > self.max_pages


def count_pdf_pages(pdf_path: Path) -> int:
    """Return the page count for an existing PDF file."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is not installed. Install it to count PDF pages."
        ) from exc

    pdf_path = pdf_path.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_path.name}")

    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def count_docx_pages(docx_path: Path) -> int:
    """
    Return the page count for a .docx file by converting to PDF via Word.

    Requires Microsoft Word (docx2pdf) and the pypdf package.
    """
    try:
        from docx2pdf import convert
    except ImportError as exc:
        raise RuntimeError(
            "docx2pdf is not installed. Install project requirements first."
        ) from exc

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is not installed. Install it to count PDF pages."
        ) from exc

    docx_path = docx_path.resolve()
    if not docx_path.is_file():
        raise FileNotFoundError(f"Document not found: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx file, got: {docx_path.name}")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)

    try:
        convert(str(docx_path), str(pdf_path))
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    finally:
        if pdf_path.is_file():
            pdf_path.unlink()


def check_page_limit(
    docx_path: Path,
    document_type: str = "resume",
    config: Config | None = None,
) -> PageCheckResult:
    """
    Compare a generated document's page count to config limits.

    Run this after Fill_Resume (or similar) creates the output .docx.
    """
    cfg = config or load_config()
    docx_path = docx_path.resolve()
    max_pages = cfg.max_pages_for(document_type)

    if not cfg.page_check_enabled(document_type):
        return PageCheckResult(
            within_limit=True,
            page_count=None,
            max_pages=max_pages,
            document_type=document_type,
            docx_path=docx_path,
            skipped=True,
        )

    if not docx_path.is_file():
        return PageCheckResult(
            within_limit=False,
            page_count=None,
            max_pages=max_pages,
            document_type=document_type,
            docx_path=docx_path,
            issues=[ValidationIssue("file", f"not found: {docx_path}")],
        )

    try:
        page_count = count_docx_pages(docx_path)
    except (RuntimeError, FileNotFoundError, ValueError, OSError) as exc:
        return PageCheckResult(
            within_limit=False,
            page_count=None,
            max_pages=max_pages,
            document_type=document_type,
            docx_path=docx_path,
            issues=[ValidationIssue("pages", str(exc))],
        )

    within_limit = page_count <= max_pages
    issues: list[ValidationIssue] = []
    if not within_limit:
        issues.append(
            ValidationIssue(
                "pages",
                (
                    f"{page_count} pages in {docx_path.name} "
                    f"(limit {max_pages} for {document_type})"
                ),
                warning=True,
            )
        )

    return PageCheckResult(
        within_limit=within_limit,
        page_count=page_count,
        max_pages=max_pages,
        document_type=document_type,
        docx_path=docx_path,
        issues=issues,
    )


def check_pdf_page_limit(
    pdf_path: Path,
    document_type: str = "resume",
    config: Config | None = None,
) -> PageCheckResult:
    """
    Compare a generated PDF's page count to config limits.

    Use the PDF produced by Pdf_Engine rather than re-converting from .docx.
    """
    cfg = config or load_config()
    pdf_path = pdf_path.resolve()
    max_pages = cfg.max_pages_for(document_type)

    if not cfg.page_check_enabled(document_type):
        return PageCheckResult(
            within_limit=True,
            page_count=None,
            max_pages=max_pages,
            document_type=document_type,
            docx_path=pdf_path,
            skipped=True,
        )

    if not pdf_path.is_file():
        return PageCheckResult(
            within_limit=False,
            page_count=None,
            max_pages=max_pages,
            document_type=document_type,
            docx_path=pdf_path,
            issues=[ValidationIssue("file", f"not found: {pdf_path}")],
        )

    try:
        page_count = count_pdf_pages(pdf_path)
    except (RuntimeError, FileNotFoundError, ValueError, OSError) as exc:
        return PageCheckResult(
            within_limit=False,
            page_count=None,
            max_pages=max_pages,
            document_type=document_type,
            docx_path=pdf_path,
            issues=[ValidationIssue("pages", str(exc))],
        )

    within_limit = page_count <= max_pages
    issues: list[ValidationIssue] = []
    if not within_limit:
        issues.append(
            ValidationIssue(
                "pages",
                (
                    f"{page_count} pages in {pdf_path.name} "
                    f"(limit {max_pages} for {document_type})"
                ),
                warning=True,
            )
        )

    return PageCheckResult(
        within_limit=within_limit,
        page_count=page_count,
        max_pages=max_pages,
        document_type=document_type,
        docx_path=pdf_path,
        issues=issues,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check a generated .docx against page limits in config/settings.json.",
    )
    parser.add_argument("docx", type=Path, help="Path to the generated .docx file.")
    parser.add_argument(
        "-t",
        "--type",
        choices=KNOWN_DOCUMENT_TYPES,
        default="resume",
        help="Document type for limit lookup (default: resume).",
    )
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

    result = check_page_limit(args.docx, args.type, config)

    if result.skipped:
        print(f"Page check skipped for {args.type} (disabled in settings).")
        return 0

    if result.page_count is not None and result.within_limit:
        print(
            f"OK: {result.docx_path.name} is {result.page_count} page(s) "
            f"(limit: {result.max_pages} for {result.document_type})."
        )
        return 0

    for message in result.error_messages():
        print(message, file=sys.stderr)

    for message in result.warning_messages():
        print(message, file=sys.stderr)

    return 0 if result.within_limit else 1


if __name__ == "__main__":
    raise SystemExit(main())
