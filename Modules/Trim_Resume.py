#!/usr/bin/env python3
"""
Remove one resume bullet per call when trimming for page limits.

Uses cfg.trim.order (list of TrimStep]) passed in from Main — this module does not
load settings.json. cfg.trim.enabled and cfg.trim.max_attempts are enforced by Main
only; they are documented here for pipeline context.

Mutates ResumeData.bullet_groups in place. Main should pass the same object to
fill_resume(..., data=data) on the next generation attempt.

Does not call fill_resume, PDF conversion, or page checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.Loader import TrimStep

from Modules.Fill_Resume import ResumeData


@dataclass
class TrimState:
    """Cursor for the next trim attempt in cfg.trim.order."""

    order_index: int = 0
    empty_skips: int = 0


@dataclass
class TrimResult:
    """Outcome of a single trim_one_bullet call."""

    removed: bool
    section: str | None
    bullet_text: str | None
    next_state: TrimState
    exhausted: bool = False


def initial_trim_state() -> TrimState:
    """Start trimming from the first step in trim.order."""
    return TrimState()


def trim_one_bullet(
    data: ResumeData,
    order: list[TrimStep],
    state: TrimState,
) -> TrimResult:
    """
    Try to remove one bullet according to trim.order.

    One call performs at most one removal. If the current section is empty, advances
    through order until a bullet is removed or every section has been tried once.

    Args:
        data: Resume data (bullet_groups mutated in place when removed=True).
        order: cfg.trim.order from Config (Main passes this in).
        state: Current position in order.

    Returns:
        TrimResult with updated next_state.order_index (wraps after the last step).
    """
    if not order:
        return TrimResult(
            removed=False,
            section=None,
            bullet_text=None,
            next_state=state,
            exhausted=True,
        )

    count = len(order)
    index = state.order_index % count
    empty_skips = state.empty_skips

    for _ in range(count):
        step = order[index]

        if step.remove != "bullets":
            raise ValueError(
                f'Unsupported trim remove type "{step.remove}" '
                f'(section "{step.section}"). Only "bullets" is supported.'
            )

        bullets = data.bullet_groups.get(step.section)
        if bullets:
            removed_text = bullets.pop()
            next_index = (index + 1) % count
            return TrimResult(
                removed=True,
                section=step.section,
                bullet_text=removed_text,
                next_state=TrimState(order_index=next_index, empty_skips=empty_skips),
                exhausted=False,
            )

        empty_skips += 1
        index = (index + 1) % count

    return TrimResult(
        removed=False,
        section=None,
        bullet_text=None,
        next_state=TrimState(order_index=index, empty_skips=empty_skips),
        exhausted=True,
    )
