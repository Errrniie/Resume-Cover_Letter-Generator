#!/usr/bin/env python3
"""
Orchestrate resume generation: config, validation, application folders, fill, PDF, page check.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Modules.Application_Path import resolve_application_path_from_data
from Modules.Application_Tracker import (
    try_record_cover_letter_generated,
    try_record_resume_generated,
)
from Modules.Resume_Md import save_temporary_resume_md
from Modules.Fill_Cover_Letter import fill_cover_letter, parse_cover_letter_data
from Modules.Fill_Resume import fill_resume, parse_resume_data
from Modules.Pdf_Engine import convert_docx_to_pdf, pdf_path_for_docx
from Modules.Trim_Resume import TrimState, initial_trim_state, trim_one_bullet
from config.Cover_Letter_Validator import validate_cover_letter_data
from config.Loader import Config, load_config, resolve_template_path
from config.Log_Path import resolve_log_file_path
from config.Metadata_Validator import validate_metadata
from config.Page_Checker import PageCheckResult, check_pdf_page_limit
from config.Pipeline_Progress import (
    CL_PHASE_APPLICATION_FOLDER,
    CL_PHASE_COMPLETED,
    CL_PHASE_CONVERT_PDF,
    CL_PHASE_FAILED,
    CL_PHASE_FILL_DOCX,
    CL_PHASE_PAGE_CHECK,
    CL_PHASE_STARTED,
    CL_PHASE_VALIDATE,
    PHASE_APPLICATION_FOLDER,
    PHASE_COMPLETED,
    PHASE_CONVERT_PDF,
    PHASE_FAILED,
    PHASE_FILL_DOCX,
    PHASE_PAGE_CHECK_FINAL,
    PHASE_PAGE_CHECK_INITIAL,
    PHASE_STARTED,
    PHASE_TRIM,
    PHASE_VALIDATE_BULLETS,
    PHASE_VALIDATE_METADATA,
    PipelineProgress,
    completed_step,
    cover_letter_completed_step,
    cover_letter_pipeline_total_steps,
    page_check_final_step,
    pipeline_total_steps,
    trim_start_step,
)
from config.Validator import validate_data
from config.logging_setup import configure_run_logging, shutdown_run_logging

log = logging.getLogger("resume.pipeline")

__all__ = [
    "CoverLetterPipelineResult",
    "PipelineProgress",
    "PipelineResult",
    "load_json_input",
    "run_cover_letter_pipeline",
    "run_pipeline",
    "sanitize_filename_part",
]

RESUME_FILENAME_PREFIX = "Ernesto_Carlton_Resume"
COVER_LETTER_FILENAME_PREFIX = "Ernesto_Carlton_Cover_Letter"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class PipelineResult:
    """Outcome of a successful resume generation run."""

    position_dir: Path
    docx_path: Path
    pdf_path: Path
    page_count: int | None
    max_pages: int
    over_page_limit: bool
    page_check_skipped: bool
    bullets_trimmed: list[str] = field(default_factory=list)
    log_path: Path | None = None


@dataclass
class CoverLetterPipelineResult:
    """Outcome of a successful cover letter generation run."""

    position_dir: Path
    docx_path: Path
    pdf_path: Path
    page_count: int | None
    max_pages: int
    over_page_limit: bool
    page_check_skipped: bool
    log_path: Path | None = None


def sanitize_filename_part(text: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("", text)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("._")


def _emit_progress(
    on_progress: Callable[[PipelineProgress], None] | None,
    *,
    phase: str,
    message: str,
    step: int,
    total_steps: int,
    detail: str | None = None,
) -> None:
    if on_progress is not None:
        on_progress(
            PipelineProgress(
                phase=phase,
                message=message,
                step=step,
                total_steps=total_steps,
                detail=detail,
            )
        )


def load_json_input(source: Path | dict[str, Any]) -> dict[str, Any]:
    """Load resume JSON from a file path or an in-memory dict."""
    if isinstance(source, dict):
        return source
    with source.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("JSON root must be an object")
    return raw


def unique_resume_docx_path(position_dir: Path, raw: dict[str, Any]) -> Path:
    """Build Ernesto_Carlton_Resume_{Company}_{Position}.docx with _2, _3 if needed."""
    company = sanitize_filename_part(str(raw.get("company", "")))
    position = sanitize_filename_part(str(raw.get("position", "")))
    if not company or not position:
        raise ValueError(
            'JSON must include non-empty "company" and "position" for output naming'
        )

    filename = f"{RESUME_FILENAME_PREFIX}_{company}_{position}.docx"
    candidate = position_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    for suffix in range(2, 1000):
        path = position_dir / f"{stem}_{suffix}.docx"
        if not path.exists():
            return path
    raise RuntimeError(f"Could not find unused filename for {filename}")


def resume_template_path(config: Config) -> Path:
    template = config.template("resume")
    if template is None or not template.enabled or template.path is None:
        raise ValueError('Resume template is not enabled or has no path in settings.json')
    path = resolve_template_path(template)
    if not path.is_file():
        raise FileNotFoundError(f"Resume template not found: {path}")
    return path


def unique_cover_letter_docx_path(position_dir: Path, raw: dict[str, Any]) -> Path:
    """Build Ernesto_Carlton_Cover_Letter_{Company}_{Position}.docx with _2, _3 if needed."""
    company = sanitize_filename_part(str(raw.get("company", "")))
    position = sanitize_filename_part(str(raw.get("position", "")))
    if not company or not position:
        raise ValueError(
            'JSON must include non-empty "company" and "position" for output naming'
        )

    filename = f"{COVER_LETTER_FILENAME_PREFIX}_{company}_{position}.docx"
    candidate = position_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    for suffix in range(2, 1000):
        path = position_dir / f"{stem}_{suffix}.docx"
        if not path.exists():
            return path
    raise RuntimeError(f"Could not find unused filename for {filename}")


def cover_letter_template_path(config: Config) -> Path:
    template = config.template("cover_letter")
    if template is None or not template.enabled or template.path is None:
        raise ValueError(
            "Cover letter template is not enabled or has no path in settings.json"
        )
    path = resolve_template_path(template)
    if not path.is_file():
        raise FileNotFoundError(f"Cover letter template not found: {path}")
    return path


def _raise_validation_error(validation) -> None:
    messages = validation.messages()
    detail = "\n".join(f"  - {m}" for m in messages)
    raise ValueError(f"JSON validation failed:\n{detail}")


def _raise_cover_letter_validation_error(validation) -> None:
    messages = validation.messages()
    detail = "\n".join(f"  - {m}" for m in messages)
    raise ValueError(f"Cover letter validation failed:\n{detail}")


def _page_check_progress_message(page_result: PageCheckResult) -> str:
    if page_result.skipped:
        return "Page check skipped (disabled in settings)."
    if page_result.page_count is not None:
        status = "OVER LIMIT" if page_result.over_page_limit else "OK"
        return (
            f"Page check: {page_result.page_count} page(s) "
            f"(limit {page_result.max_pages}) — {status}"
        )
    if page_result.error_messages():
        return page_result.error_messages()[0]
    return "Page check completed."


def _report_page_check(
    page_result: PageCheckResult,
    *,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    step: int | None = None,
    total_steps: int | None = None,
    phase: str = PHASE_PAGE_CHECK_FINAL,
    pipeline_log: logging.Logger | None = None,
) -> None:
    active_log = pipeline_log or log
    for message in page_result.warning_messages():
        print(message, file=sys.stderr)
        active_log.warning(message)
    for message in page_result.error_messages():
        print(message, file=sys.stderr)
        active_log.error(message)

    progress_message = _page_check_progress_message(page_result)
    if on_progress is not None and step is not None and total_steps is not None:
        _emit_progress(
            on_progress,
            phase=phase,
            message=progress_message,
            step=step,
            total_steps=total_steps,
        )

    if page_result.skipped:
        print("Page check skipped (disabled in settings).")
        active_log.info("Page check skipped (disabled in settings)")
    elif page_result.page_count is not None:
        status = "OVER LIMIT" if page_result.over_page_limit else "OK"
        print(
            f"Page check ({status}): {page_result.page_count} page(s) "
            f"(limit {page_result.max_pages})."
        )
        active_log.info(
            "Page check (%s): %s page(s) (limit %s)",
            status,
            page_result.page_count,
            page_result.max_pages,
        )


def _trim_for_page_limit(
    resume_data,
    docx_path: Path,
    template_path: Path,
    cfg: Config,
    *,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    total_steps: int,
    initial_page_step: int,
) -> tuple[PageCheckResult, list[str]]:
    """
    While over the page limit, remove one bullet per cfg.trim.order step (round-robin),
    then regenerate docx/pdf and re-check. Never removes a whole section at once.
    """
    pdf_path = pdf_path_for_docx(docx_path)
    page_result = check_pdf_page_limit(pdf_path, document_type="resume", config=cfg)
    bullets_trimmed: list[str] = []

    _report_page_check(
        page_result,
        on_progress=on_progress,
        step=initial_page_step,
        total_steps=total_steps,
        phase=PHASE_PAGE_CHECK_INITIAL,
    )

    if not cfg.trim.enabled or page_result.skipped or not page_result.over_page_limit:
        return page_result, bullets_trimmed

    trim_state: TrimState = initial_trim_state()
    attempts = 0
    trim_step = trim_start_step()

    while page_result.over_page_limit and attempts < cfg.trim.max_attempts:
        trim_result = trim_one_bullet(resume_data, cfg.trim.order, trim_state)
        trim_state = trim_result.next_state
        attempts += 1

        if trim_result.exhausted or not trim_result.removed:
            print(
                "Trim: no more bullets available to remove.",
                file=sys.stderr,
            )
            log.info("Trim: no more bullets available to remove")
            _emit_progress(
                on_progress,
                phase=PHASE_TRIM,
                message="Trim: no more bullets available to remove.",
                step=trim_step,
                total_steps=total_steps,
            )
            break

        label = (
            f"{trim_result.section}: {trim_result.bullet_text}"
            if trim_result.bullet_text
            else trim_result.section or "unknown"
        )
        bullets_trimmed.append(label)
        print(f"Trim: removed bullet from {label}", file=sys.stderr)
        log.info("Trim: removed bullet from %s", label)

        _emit_progress(
            on_progress,
            phase=PHASE_TRIM,
            message=f"Trim: removed bullet from {label}",
            step=trim_step,
            total_steps=total_steps,
        )
        _emit_progress(
            on_progress,
            phase=PHASE_TRIM,
            message="Regenerating DOCX and PDF…",
            step=trim_step,
            total_steps=total_steps,
        )

        fill_resume(template_path, docx_path, data=resume_data)
        convert_docx_to_pdf(docx_path, pdf_path)
        page_result = check_pdf_page_limit(pdf_path, document_type="resume", config=cfg)
        trim_step += 1

    return page_result, bullets_trimmed


def run_pipeline(
    json_source: Path | dict[str, Any],
    *,
    config: Config | None = None,
    settings_path: Path | None = None,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    job_sequence: int | None = None,
) -> PipelineResult:
    """
    Run the full resume pipeline.

    json_source: Path to a JSON file or a dict (for integration with other tools).
    on_progress: Optional callback invoked synchronously after each step. Safe to call
        from a worker thread; must not touch Tk widgets (GUI should use queue + after()).
    """
    cfg = config or load_config(settings_path)
    total_steps = pipeline_total_steps(cfg.trim.max_attempts)
    current_step = 1

    input_label = str(json_source) if isinstance(json_source, Path) else "dict input"
    raw = load_json_input(json_source)

    log_path = resolve_log_file_path(raw, document_type="resume")
    configure_run_logging(log_path, document_type="resume")
    log.info("Run started; input=%s", input_label)

    try:
        _emit_progress(
            on_progress,
            phase=PHASE_STARTED,
            message="Run started.",
            step=current_step,
            total_steps=total_steps,
            detail=input_label,
        )

        current_step = 2
        _emit_progress(
            on_progress,
            phase=PHASE_VALIDATE_METADATA,
            message="Validating metadata…",
            step=current_step,
            total_steps=total_steps,
        )
        meta = validate_metadata(raw)
        if not meta.valid:
            log.error("Metadata validation failed: %s", "; ".join(meta.messages()))
            _raise_validation_error(meta)
        log.info("Metadata validation passed")
        _emit_progress(
            on_progress,
            phase=PHASE_VALIDATE_METADATA,
            message="Metadata validation passed.",
            step=current_step,
            total_steps=total_steps,
        )

        current_step = 3
        _emit_progress(
            on_progress,
            phase=PHASE_VALIDATE_BULLETS,
            message="Validating bullets…",
            step=current_step,
            total_steps=total_steps,
        )
        validation = validate_data(raw, cfg)
        if not validation.valid:
            log.error("Bullet validation failed: %s", "; ".join(validation.messages()))
            _raise_validation_error(validation)
        log.info("Bullet validation passed")
        _emit_progress(
            on_progress,
            phase=PHASE_VALIDATE_BULLETS,
            message="Bullet validation passed.",
            step=current_step,
            total_steps=total_steps,
        )

        try:
            md_result = save_temporary_resume_md(raw)
            log.info("Resume snapshot MD: %s", md_result.path)
        except Exception as exc:
            log.warning("Resume snapshot MD not written: %s", exc)

        current_step = 4
        position_dir = resolve_application_path_from_data(raw)
        log.info("Application folder: %s", position_dir)
        _emit_progress(
            on_progress,
            phase=PHASE_APPLICATION_FOLDER,
            message=f"Position folder: {position_dir}",
            step=current_step,
            total_steps=total_steps,
            detail=str(position_dir),
        )

        docx_path = unique_resume_docx_path(position_dir, raw)
        template_path = resume_template_path(cfg)
        resume_data = parse_resume_data(raw)

        current_step = 5
        _emit_progress(
            on_progress,
            phase=PHASE_FILL_DOCX,
            message="Creating DOCX…",
            step=current_step,
            total_steps=total_steps,
        )
        fill_resume(template_path, docx_path, data=resume_data)
        log.info("Created DOCX: %s", docx_path)
        _emit_progress(
            on_progress,
            phase=PHASE_FILL_DOCX,
            message=f"Created DOCX: {docx_path.name}",
            step=current_step,
            total_steps=total_steps,
            detail=str(docx_path),
        )

        current_step = 6
        _emit_progress(
            on_progress,
            phase=PHASE_CONVERT_PDF,
            message="Converting to PDF… (Word may take a while)",
            step=current_step,
            total_steps=total_steps,
        )
        pdf_path = convert_docx_to_pdf(docx_path, pdf_path_for_docx(docx_path))
        log.info("Created PDF: %s", pdf_path)
        _emit_progress(
            on_progress,
            phase=PHASE_CONVERT_PDF,
            message=f"Created PDF: {pdf_path.name}",
            step=current_step,
            total_steps=total_steps,
            detail=str(pdf_path),
        )

        page_result, bullets_trimmed = _trim_for_page_limit(
            resume_data,
            docx_path,
            template_path,
            cfg,
            on_progress=on_progress,
            total_steps=total_steps,
            initial_page_step=7,
        )
        final_page_step = page_check_final_step(cfg.trim.max_attempts)
        _report_page_check(
            page_result,
            on_progress=on_progress,
            step=final_page_step,
            total_steps=total_steps,
            phase=PHASE_PAGE_CHECK_FINAL,
        )

        log.info(
            "Run finished successfully (over_page_limit=%s, page_check_skipped=%s)",
            page_result.over_page_limit,
            page_result.skipped,
        )

        _emit_progress(
            on_progress,
            phase=PHASE_COMPLETED,
            message="Run finished successfully.",
            step=completed_step(cfg.trim.max_attempts),
            total_steps=total_steps,
        )

        try_record_resume_generated(
            str(raw.get("company", "")),
            str(raw.get("position", "")),
            job_sequence=job_sequence,
        )

        return PipelineResult(
            position_dir=position_dir,
            docx_path=docx_path,
            pdf_path=pdf_path,
            page_count=page_result.page_count,
            max_pages=page_result.max_pages,
            over_page_limit=page_result.over_page_limit,
            page_check_skipped=page_result.skipped,
            bullets_trimmed=bullets_trimmed,
            log_path=log_path,
        )
    except Exception as exc:
        log.exception("Run failed")
        summary = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        _emit_progress(
            on_progress,
            phase=PHASE_FAILED,
            message=f"Generation failed: {summary}",
            step=current_step,
            total_steps=total_steps,
            detail=summary,
        )
        raise
    finally:
        shutdown_run_logging()


def run_cover_letter_pipeline(
    json_source: Path | dict[str, Any],
    *,
    config: Config | None = None,
    settings_path: Path | None = None,
    on_progress: Callable[[PipelineProgress], None] | None = None,
    job_sequence: int | None = None,
) -> CoverLetterPipelineResult:
    """
    Run the cover letter pipeline (fill, PDF, page check; no trim).

    Cover letter JSON must use the same company and position as the resume so outputs
    land in Applications/{company}/{position}/.
    """
    cfg = config or load_config(settings_path)
    total_steps = cover_letter_pipeline_total_steps()
    current_step = 1

    input_label = str(json_source) if isinstance(json_source, Path) else "dict input"
    raw = load_json_input(json_source)

    log_path = resolve_log_file_path(raw, document_type="cover_letter")
    cl_log = configure_run_logging(log_path, document_type="cover_letter")
    cl_log.info("Cover letter run started; input=%s", input_label)

    try:
        _emit_progress(
            on_progress,
            phase=CL_PHASE_STARTED,
            message="Cover letter run started.",
            step=current_step,
            total_steps=total_steps,
            detail=input_label,
        )

        current_step = 2
        _emit_progress(
            on_progress,
            phase=CL_PHASE_VALIDATE,
            message="Validating cover letter JSON…",
            step=current_step,
            total_steps=total_steps,
        )
        validation = validate_cover_letter_data(raw)
        if not validation.valid:
            cl_log.error(
                "Cover letter validation failed: %s",
                "; ".join(validation.messages()),
            )
            _raise_cover_letter_validation_error(validation)
        cl_log.info("Cover letter validation passed")
        _emit_progress(
            on_progress,
            phase=CL_PHASE_VALIDATE,
            message="Cover letter validation passed.",
            step=current_step,
            total_steps=total_steps,
        )

        current_step = 3
        position_dir = resolve_application_path_from_data(raw)
        cl_log.info("Application folder: %s", position_dir)
        _emit_progress(
            on_progress,
            phase=CL_PHASE_APPLICATION_FOLDER,
            message=f"Position folder: {position_dir}",
            step=current_step,
            total_steps=total_steps,
            detail=str(position_dir),
        )

        docx_path = unique_cover_letter_docx_path(position_dir, raw)
        template_path = cover_letter_template_path(cfg)
        letter_data = parse_cover_letter_data(raw)

        current_step = 4
        _emit_progress(
            on_progress,
            phase=CL_PHASE_FILL_DOCX,
            message="Creating cover letter DOCX…",
            step=current_step,
            total_steps=total_steps,
        )
        fill_cover_letter(template_path, docx_path, data=letter_data)
        cl_log.info("Created DOCX: %s", docx_path)
        _emit_progress(
            on_progress,
            phase=CL_PHASE_FILL_DOCX,
            message=f"Created DOCX: {docx_path.name}",
            step=current_step,
            total_steps=total_steps,
            detail=str(docx_path),
        )

        current_step = 5
        _emit_progress(
            on_progress,
            phase=CL_PHASE_CONVERT_PDF,
            message="Converting to PDF… (Word may take a while)",
            step=current_step,
            total_steps=total_steps,
        )
        pdf_path = convert_docx_to_pdf(docx_path, pdf_path_for_docx(docx_path))
        cl_log.info("Created PDF: %s", pdf_path)
        _emit_progress(
            on_progress,
            phase=CL_PHASE_CONVERT_PDF,
            message=f"Created PDF: {pdf_path.name}",
            step=current_step,
            total_steps=total_steps,
            detail=str(pdf_path),
        )

        current_step = 6
        page_result = check_pdf_page_limit(
            pdf_path, document_type="cover_letter", config=cfg
        )
        _report_page_check(
            page_result,
            on_progress=on_progress,
            step=current_step,
            total_steps=total_steps,
            phase=CL_PHASE_PAGE_CHECK,
            pipeline_log=cl_log,
        )

        cl_log.info(
            "Cover letter run finished (over_page_limit=%s, page_check_skipped=%s)",
            page_result.over_page_limit,
            page_result.skipped,
        )

        _emit_progress(
            on_progress,
            phase=CL_PHASE_COMPLETED,
            message="Cover letter run finished successfully.",
            step=cover_letter_completed_step(),
            total_steps=total_steps,
        )

        try_record_cover_letter_generated(
            str(raw.get("company", "")),
            str(raw.get("position", "")),
            job_sequence=job_sequence,
        )

        return CoverLetterPipelineResult(
            position_dir=position_dir,
            docx_path=docx_path,
            pdf_path=pdf_path,
            page_count=page_result.page_count,
            max_pages=page_result.max_pages,
            over_page_limit=page_result.over_page_limit,
            page_check_skipped=page_result.skipped,
            log_path=log_path,
        )
    except Exception as exc:
        cl_log.exception("Cover letter run failed")
        summary = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        _emit_progress(
            on_progress,
            phase=CL_PHASE_FAILED,
            message=f"Cover letter generation failed: {summary}",
            step=current_step,
            total_steps=total_steps,
            detail=summary,
        )
        raise
    finally:
        shutdown_run_logging()


def launch_gui() -> None:
    """Open the desktop GUI (CustomTkinter)."""
    from Gui import main as gui_main

    gui_main()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resume generator. Opens the GUI when run with no arguments.",
    )
    parser.add_argument(
        "json",
        nargs="?",
        type=Path,
        default=None,
        help="Path to JSON data (CLI mode). Omit to open the GUI.",
    )
    parser.add_argument(
        "--cover-letter",
        action="store_true",
        help="Run cover letter pipeline instead of resume (requires json path).",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to settings.json (default: config/settings.json). CLI only.",
    )
    return parser.parse_args(argv)


def run_cli(json_path: Path, *, settings_path: Path | None = None) -> int:
    """Generate a resume from JSON on the command line."""
    try:
        config = load_config(settings_path)
        result = run_pipeline(json_path.resolve(), config=config)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Position folder: {result.position_dir}")
    print(f"Created: {result.docx_path}")
    print(f"Created: {result.pdf_path}")
    if result.log_path is not None:
        print(f"Log: {result.log_path}")
    if result.bullets_trimmed:
        print("Bullets trimmed:")
        for entry in result.bullets_trimmed:
            print(f"  - {entry}")
    if result.over_page_limit:
        print("over_page_limit: true")
    else:
        print("over_page_limit: false")
    return 0


def run_cli_cover_letter(
    json_path: Path, *, settings_path: Path | None = None
) -> int:
    """Generate a cover letter from JSON on the command line."""
    try:
        config = load_config(settings_path)
        result = run_cover_letter_pipeline(json_path.resolve(), config=config)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Position folder: {result.position_dir}")
    print(f"Created: {result.docx_path}")
    print(f"Created: {result.pdf_path}")
    if result.log_path is not None:
        print(f"Log: {result.log_path}")
    if result.over_page_limit:
        print("over_page_limit: true")
    else:
        print("over_page_limit: false")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.json is None:
        if args.cover_letter:
            print("Error: --cover-letter requires a JSON file path.", file=sys.stderr)
            return 1
        launch_gui()
        return 0
    if args.cover_letter:
        return run_cli_cover_letter(args.json, settings_path=args.config)
    return run_cli(args.json, settings_path=args.config)


if __name__ == "__main__":
    raise SystemExit(main())
