"""Shared validation issue types used across config checks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationIssue:
    """One problem or warning found during validation."""

    location: str
    message: str
    warning: bool = False

    def format(self) -> str:
        prefix = "WARNING" if self.warning else "ERROR"
        return f"{prefix} {self.location}: {self.message}"


@dataclass
class ValidationResult:
    """Outcome of validating JSON bullet content."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    bullet_groups: dict[str, list[str]] = field(default_factory=dict)

    def messages(self) -> list[str]:
        return [issue.format() for issue in self.issues]

    def error_messages(self) -> list[str]:
        """Non-warning issues only (kept for compatibility)."""
        return [issue.format() for issue in self.issues if not issue.warning]

    def warning_messages(self) -> list[str]:
        return [issue.format() for issue in self.issues if issue.warning]
