#!/usr/bin/env python3
"""
Future: trim cover letter content when over page limit.

Not implemented in phase 1. Main pipeline will call this when wired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def trim_cover_letter(
    docx_path: Path,
    *,
    config: Any = None,
) -> Path:
    """
    TODO: Remove content per settings when cover letter exceeds page limit.

    Raises:
        NotImplementedError: Until trim rules and settings are defined.
    """
    raise NotImplementedError(
        "Cover letter trim is not implemented yet (see config/Cover_Letter_Config.py)."
    )
