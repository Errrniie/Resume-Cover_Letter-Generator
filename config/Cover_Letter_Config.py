"""Cover letter constants (validation fields; future trim/page hooks)."""

from __future__ import annotations

REQUIRED_COVER_LETTER_FIELDS: tuple[str, ...] = (
    "company",
    "position",
    "company_address",
    "technical_area_from_job",
    "your_project_that_matches",
    "specific_challenge_you_solved",
    "what_you_did",
    "quantifiable_outcome",
    "skill_from_job",
    "previous_job_title",
    "work_experience_lesson",
    "why_this_company_unique",
    "logistics_requirement",
)

# Template tokens that differ from JSON key spelling (1:1 via alias).
PLACEHOLDER_ALIASES: dict[str, tuple[str, ...]] = {
    "company_address": ("{{ company address }}",),
}

# Future: trim / page-check phases (not implemented).
TRIM_PHASE_STUB = "trim_cover_letter"
PAGE_CHECK_PHASE_STUB = "page_check_cover_letter"
