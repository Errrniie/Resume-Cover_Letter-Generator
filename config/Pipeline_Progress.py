"""Progress events for resume pipeline runs (GUI / CLI callbacks)."""

from __future__ import annotations

from dataclasses import dataclass

# Machine-readable phase ids (stable for GUI mapping).
PHASE_STARTED = "started"
PHASE_VALIDATE_METADATA = "validate_metadata"
PHASE_VALIDATE_BULLETS = "validate_bullets"
PHASE_APPLICATION_FOLDER = "application_folder"
PHASE_FILL_DOCX = "fill_docx"
PHASE_CONVERT_PDF = "convert_pdf"
PHASE_PAGE_CHECK_INITIAL = "page_check_initial"
PHASE_TRIM = "trim"
PHASE_PAGE_CHECK_FINAL = "page_check_final"
PHASE_COMPLETED = "completed"
PHASE_FAILED = "failed"

# Steps 1–7: through initial page check. Steps 8..7+max_attempts: trim slots.
_STEPS_BEFORE_TRIM = 7


@dataclass(frozen=True)
class PipelineProgress:
    """One progress update for a pipeline run."""

    phase: str
    message: str
    step: int
    total_steps: int
    detail: str | None = None


def pipeline_total_steps(max_trim_attempts: int) -> int:
    """
    Fixed total for the progress bar: base pipeline + trim slots + final page check + completed.

    Trim slots are reserved even when trim does not run (bar may jump forward without going back).
    """
    return _STEPS_BEFORE_TRIM + max_trim_attempts + 2


def trim_start_step() -> int:
    """First 1-based step index reserved for trim iterations."""
    return _STEPS_BEFORE_TRIM + 1


def page_check_final_step(max_trim_attempts: int) -> int:
    return trim_start_step() + max_trim_attempts


def completed_step(max_trim_attempts: int) -> int:
    return pipeline_total_steps(max_trim_attempts)


# Cover letter pipeline (no trim slots).
CL_PHASE_STARTED = "cover_letter_started"
CL_PHASE_VALIDATE = "cover_letter_validate"
CL_PHASE_APPLICATION_FOLDER = "cover_letter_application_folder"
CL_PHASE_FILL_DOCX = "cover_letter_fill_docx"
CL_PHASE_CONVERT_PDF = "cover_letter_convert_pdf"
CL_PHASE_PAGE_CHECK = "cover_letter_page_check"
CL_PHASE_COMPLETED = "cover_letter_completed"
CL_PHASE_FAILED = "cover_letter_failed"

_COVER_LETTER_TOTAL_STEPS = 7


def cover_letter_pipeline_total_steps() -> int:
    """Fixed total for cover letter progress bar (no trim)."""
    return _COVER_LETTER_TOTAL_STEPS


def cover_letter_completed_step() -> int:
    return _COVER_LETTER_TOTAL_STEPS
