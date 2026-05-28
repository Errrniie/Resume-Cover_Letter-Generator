#!/usr/bin/env python3
"""
Desktop GUI for resume generation (CustomTkinter).

Uses Main.run_pipeline / run_cover_letter_pipeline and config for settings (see Error.md).
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Main import (
    PROJECT_ROOT as MAIN_ROOT,
    CoverLetterPipelineResult,
    PipelineProgress,
    PipelineResult,
    run_cover_letter_pipeline,
    run_pipeline,
)
from config.Cover_Letter_Validator import validate_cover_letter_json_file
from config.Pipeline_Progress import CL_PHASE_FAILED, PHASE_FAILED, PHASE_TRIM
from config import (
    DEFAULT_SETTINGS_PATH,
    config_from_dict,
    config_to_dict,
    load_config,
    save_config,
)
from config.Validator import validate_json_file
from Modules.Application_Tracker import (
    ApplicationRecord,
    application_stats,
    load_application_log,
    tracker_path,
    try_record_job_start,
)
from Modules.Job_Md import (
    JobMdSaveResult,
    get_current_job_md_path,
    job_md_root,
    save_temporary_job_md,
)
from Modules.Application_Delete import (
    delete_application_file,
    delete_position_folder,
    is_deletable_application_path,
)
from Modules.Resume_Md import get_current_resume_md_path, resume_md_root

APPLICATIONS_DIR = MAIN_ROOT / "Applications"
RESUME_EXTENSIONS = {".docx", ".pdf"}
APPLICATIONS_PANEL_FONT_SIZE = 15
APPLICATIONS_TREE_MINSIZE = 600
COLLAPSIBLE_PANEL_HEIGHT = 100
SETTINGS_NUMBER_ENTRY_WIDTH = 52
TRIM_ORDER_SLOTS = 5
TRIM_REMOVE_DEFAULT = "bullets"
TRIM_PRIORITY_ENTRY_WIDTH = 140
DEFAULT_BULLET_SECTIONS = ("greenway", "windturbine", "peizo", "mostardi", "goose")

DOC_RESUME = "resume"
DOC_COVER_LETTER = "cover_letter"
VIEW_RESUME = "Resume"
VIEW_COVER_LETTER = "Cover letter"
_DOC_TO_VIEW = {DOC_RESUME: VIEW_RESUME, DOC_COVER_LETTER: VIEW_COVER_LETTER}
RESUME_FILE_PREFIX = "Ernesto_Carlton_Resume"
COVER_LETTER_FILE_PREFIX = "Ernesto_Carlton_Cover_Letter"
DELETE_INCLUDE_PAIRED_PDF_DOCX = True
APPLICATIONS_TAB_NAME = "Applications"
_TRACKER_COLUMNS = (
    ("date", "Date", 88),
    ("company", "Company", 120),
    ("position", "Position", 140),
    ("website", "Website", 120),
    ("url", "URL", 200),
    ("resume", "Resume", 56),
    ("cover", "Cover", 56),
)
TREE_ROLE_FILE = "file"
TREE_ROLE_POSITION = "position_folder"
TREE_ROLE_COMPANY = "company"
_TREE_KNOWN_ROLES = frozenset(
    {TREE_ROLE_FILE, TREE_ROLE_POSITION, TREE_ROLE_COMPANY}
)
TreeDeleteTarget = tuple[str, Path]


def open_with_default_app(path: Path) -> None:
    """Open a file with the OS default application."""
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


def open_file_location(path: Path) -> None:
    """Open the system file manager at a file or folder."""
    path = path.resolve()
    if path.is_file():
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(path)], check=True)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=True)
        return

    if path.is_dir():
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=True)
        return

    raise FileNotFoundError(f"Path not found: {path}")


def _parse_tree_item_values(values: tuple[str, ...] | list[str]) -> TreeDeleteTarget | None:
    """Parse (role, path) from tree row values; legacy rows use a bare file path."""
    if not values or not values[0]:
        return None
    if len(values) >= 2 and values[0] in _TREE_KNOWN_ROLES:
        return values[0], Path(str(values[1])).resolve()
    return TREE_ROLE_FILE, Path(str(values[0])).resolve()


def path_for_tree_item(tree: ttk.Treeview, item_id: str) -> Path | None:
    """Return the file path stored on a tree row, if any."""
    parsed = _parse_tree_item_values(tuple(tree.item(item_id, "values")))
    if parsed is None or parsed[0] != TREE_ROLE_FILE:
        return None
    return parsed[1]


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_tree_selection(
    tree: ttk.Treeview,
) -> tuple[list[TreeDeleteTarget], str | None]:
    """
    Build a deduplicated delete plan from tree.selection().

    Each target is ("file", path) or ("position_folder", path).
    Position folders subsume file rows under them; company nodes expand to positions.
    """
    selection = tree.selection()
    if not selection:
        return [], "Select one or more files or position folders in the Applications tree."

    file_targets: dict[Path, TreeDeleteTarget] = {}
    folder_targets: dict[Path, TreeDeleteTarget] = {}
    company_dirs: list[Path] = []
    had_non_deletable = False

    for item_id in selection:
        label = str(tree.item(item_id, "text"))
        if label in ("Applications", "(folder not created yet)"):
            had_non_deletable = True
            continue

        parsed = _parse_tree_item_values(tuple(tree.item(item_id, "values")))
        if parsed is None:
            if label in ("Resume", "Cover letter", "Other"):
                had_non_deletable = True
            continue

        role, path = parsed
        if role == TREE_ROLE_FILE:
            if is_deletable_application_path(path):
                file_targets[path] = (role, path)
            else:
                had_non_deletable = True
        elif role == TREE_ROLE_POSITION:
            folder_targets[path] = (role, path)
        elif role == TREE_ROLE_COMPANY:
            company_dirs.append(path)

    for company_dir in company_dirs:
        if not company_dir.is_dir():
            continue
        for position_dir in sorted(company_dir.iterdir()):
            if position_dir.is_dir():
                resolved = position_dir.resolve()
                folder_targets[resolved] = (TREE_ROLE_POSITION, resolved)

    if folder_targets:
        file_targets = {
            key: value
            for key, value in file_targets.items()
            if not any(_path_is_under(key, folder) for folder in folder_targets)
        }

    targets = list(folder_targets.values()) + list(file_targets.values())

    if not targets:
        return [], (
            "Cannot delete the Applications root, company row alone, or group folders. "
            "Select .docx/.pdf files, a position folder, or a company to remove all "
            "positions under it."
        )

    info = None
    if had_non_deletable:
        info = "Some selected items were skipped (not deletable)."
    return targets, info


def delete_plan_confirm_message(targets: list[TreeDeleteTarget]) -> str:
    """Summary text for askyesno before delete."""
    folders = [path for role, path in targets if role == TREE_ROLE_POSITION]
    files = [path for role, path in targets if role == TREE_ROLE_FILE]
    lines = ["Delete the following?"]
    if folders:
        lines.append(f"\n{len(folders)} position folder(s) (all contents):")
        for folder in folders[:8]:
            lines.append(f"  • {folder.parent.name} / {folder.name}")
        if len(folders) > 8:
            lines.append(f"  … and {len(folders) - 8} more")
    if files:
        lines.append(f"\n{len(files)} file(s):")
        for file_path in files[:10]:
            lines.append(f"  • {file_path.name}")
        if len(files) > 10:
            lines.append(f"  … and {len(files) - 10} more")
        if DELETE_INCLUDE_PAIRED_PDF_DOCX:
            lines.append("\nMatching .docx/.pdf pairs will be deleted when present.")
    return "\n".join(lines)


def _parse_tracker_sort_time(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:26], fmt)
        except ValueError:
            continue
    return None


def sort_application_records(
    records: list[ApplicationRecord],
) -> list[ApplicationRecord]:
    """Newest first by updated, then date, then row number."""

    def sort_key(record: ApplicationRecord) -> tuple[datetime, int]:
        for candidate in (record.updated, record.date):
            parsed = _parse_tracker_sort_time(candidate)
            if parsed is not None:
                return (parsed, record.row_number)
        return (datetime.min, record.row_number)

    return sorted(records, key=sort_key, reverse=True)


def try_remove_empty_company_dir(company_dir: Path) -> None:
    """Remove company folder under Applications/ if it has no entries left."""
    try:
        if company_dir.is_dir() and not any(company_dir.iterdir()):
            company_dir.rmdir()
    except OSError:
        pass


def format_page_lines(
    result: PipelineResult | CoverLetterPipelineResult,
    *,
    document_label: str = "resume",
) -> tuple[list[str], list[str], list[str]]:
    """Build status, warning, and trim lines from a pipeline result (Error.md §10)."""
    status: list[str] = []
    warnings: list[str] = []
    trim_lines: list[str] = []

    if result.page_check_skipped:
        status.append("Page check: skipped (disabled in settings)")
        return status, warnings, trim_lines

    if result.page_count is None:
        status.append("Page count: unavailable (page check did not return a count)")
        return status, warnings, trim_lines

    label = "OVER LIMIT" if result.over_page_limit else "OK"
    status.append(
        f"Pages: {result.page_count} / limit {result.max_pages} ({label})"
    )
    if result.over_page_limit:
        warnings.append(
            f"WARNING pages: {result.page_count} pages in "
            f"{result.pdf_path.name} (limit {result.max_pages} for {document_label})"
        )
    bullets_trimmed = getattr(result, "bullets_trimmed", None)
    if bullets_trimmed:
        trim_lines.append(f"Trimmed {len(bullets_trimmed)} bullet(s) to fit page limit")
        for entry in bullets_trimmed:
            trim_lines.append(f"  - {entry}")
    return status, warnings, trim_lines


def _classify_application_file(filename: str) -> str | None:
    """Return DOC_RESUME, DOC_COVER_LETTER, or None for tree grouping."""
    lower = filename.lower()
    if lower.startswith(COVER_LETTER_FILE_PREFIX.lower()):
        return DOC_COVER_LETTER
    if lower.startswith(RESUME_FILE_PREFIX.lower()):
        return DOC_RESUME
    if "cover_letter" in lower or "cover letter" in lower:
        return DOC_COVER_LETTER
    if "resume" in lower:
        return DOC_RESUME
    return None


def populate_applications_tree(
    tree: ttk.Treeview, highlight: Path | None = None
) -> None:
    """Fill tree with Applications/{company}/{position}/… resume and cover letter files."""
    for item in tree.get_children():
        tree.delete(item)

    root_id = tree.insert("", "end", text="Applications", open=True)
    if not APPLICATIONS_DIR.is_dir():
        tree.insert(root_id, "end", text="(folder not created yet)")
        return

    highlight_resolved = highlight.resolve() if highlight else None

    for company_dir in sorted(APPLICATIONS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not company_dir.is_dir():
            continue
        company_id = tree.insert(
            root_id,
            "end",
            text=company_dir.name,
            open=False,
            values=(TREE_ROLE_COMPANY, str(company_dir.resolve())),
        )

        for position_dir in sorted(company_dir.iterdir(), key=lambda p: p.name.lower()):
            if not position_dir.is_dir():
                continue
            open_position = (
                highlight_resolved is not None
                and position_dir.resolve() == highlight_resolved
            )
            position_id = tree.insert(
                company_id,
                "end",
                text=position_dir.name,
                open=open_position,
                values=(TREE_ROLE_POSITION, str(position_dir.resolve())),
            )
            if open_position:
                tree.item(position_id, tags=("highlight",))

            resume_id = tree.insert(position_id, "end", text="Resume", open=open_position)
            cover_id = tree.insert(
                position_id, "end", text="Cover letter", open=open_position
            )
            other_id = tree.insert(position_id, "end", text="Other", open=False)

            resume_count = 0
            cover_count = 0
            other_count = 0

            for file_path in sorted(position_dir.iterdir(), key=lambda p: p.name.lower()):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in RESUME_EXTENSIONS:
                    continue
                kind = _classify_application_file(file_path.name)
                if kind == DOC_RESUME:
                    parent_id = resume_id
                    resume_count += 1
                elif kind == DOC_COVER_LETTER:
                    parent_id = cover_id
                    cover_count += 1
                else:
                    parent_id = other_id
                    other_count += 1
                tree.insert(
                    parent_id,
                    "end",
                    text=file_path.name,
                    values=(TREE_ROLE_FILE, str(file_path.resolve())),
                )

            if resume_count == 0:
                tree.delete(resume_id)
            if cover_count == 0:
                tree.delete(cover_id)
            if other_count == 0:
                tree.delete(other_id)

    tree.tag_configure("highlight", foreground="#3B8ED0")


class ResumeGui(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Resume Generator")
        self.geometry("900x620")
        self.minsize(720, 520)

        self._busy = False
        self._active_generation_type = DOC_RESUME
        self._json_entries: dict[str, ctk.CTkEntry] = {}
        self._generate_buttons: dict[str, ctk.CTkButton] = {}
        self._delete_buttons: dict[str, ctk.CTkButton] = {}
        self._trees: dict[str, ttk.Treeview] = {}
        self._status_boxes: dict[str, ctk.CTkTextbox] = {}
        self._warn_boxes: dict[str, ctk.CTkTextbox] = {}
        self._trim_boxes: dict[str, ctk.CTkTextbox] = {}
        self._collapsible_panels: dict[tuple[str, str], dict[str, object]] = {}
        self._progress_labels: dict[str, ctk.CTkLabel] = {}
        self._progress_bars: dict[str, ctk.CTkProgressBar] = {}
        self._tree_style_ready = False
        self._settings_path = DEFAULT_SETTINGS_PATH
        self._settings_widgets: dict[str, ctk.CTkBaseClass] = {}
        self._template_path_frames: dict[str, ctk.CTkFrame] = {}
        self._template_path_arrows: dict[str, ctk.CTkButton] = {}
        self._retained_default_max_pages = 1
        self._trim_remove_types: list[str] = [TRIM_REMOVE_DEFAULT] * TRIM_ORDER_SLOTS
        self._bullet_group_sections: list[str] = list(DEFAULT_BULLET_SECTIONS)
        self._progress_queue: queue.Queue[PipelineProgress] | None = None
        self._streamed_messages: set[str] = set()
        self._saw_failed_phase = False
        self._start_busy = False
        self._start_last_saved_path: Path | None = None
        self._last_job_sequence: int | None = None
        self._resume_last_md_path: Path | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self._build_start_tab(self.tabs.add("Start"))
        self._build_document_tab(self.tabs.add("Resume"), DOC_RESUME)
        self._build_document_tab(self.tabs.add("Cover Letter"), DOC_COVER_LETTER)
        self._build_applications_tab(self.tabs.add(APPLICATIONS_TAB_NAME))
        self._build_settings_tab(self.tabs.add("Settings"))

        self.refresh_tree()

    def _build_start_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(parent, text="Job posting URL:", anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4)
        )
        self._start_url_entry = ctk.CTkEntry(
            parent, placeholder_text="https://…"
        )
        self._start_url_entry.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self._start_url_entry.bind("<KeyRelease>", self._update_start_generate_state)

        ctk.CTkLabel(parent, text="Job description:", anchor="w").grid(
            row=2, column=0, sticky="w", padx=12, pady=(4, 4)
        )
        self._start_description_box = ctk.CTkTextbox(
            parent, wrap="word", activate_scrollbars=True
        )
        self._start_description_box.grid(
            row=3, column=0, sticky="nsew", padx=12, pady=(0, 8)
        )
        self._start_description_box.bind(
            "<KeyRelease>", self._update_start_generate_state
        )

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))
        self._start_generate_btn = ctk.CTkButton(
            actions,
            text="Generate",
            width=120,
            command=self._start_generate,
            state="disabled",
        )
        self._start_generate_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Open location",
            width=120,
            command=self._open_start_file_location,
        ).pack(side="left")

        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 12))
        bottom.grid_columnconfigure(0, weight=1)

        self._start_progress_label = ctk.CTkLabel(
            bottom,
            text=f"Output folder: {job_md_root()}",
            anchor="w",
            text_color="gray",
        )
        self._start_progress_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._start_progress_bar = ctk.CTkProgressBar(bottom, mode="determinate")
        self._start_progress_bar.grid(row=1, column=0, sticky="ew")
        self._start_progress_bar.set(0)

    def _start_description_text(self) -> str:
        return self._start_description_box.get("1.0", "end-1c")

    def _start_has_inputs(self) -> bool:
        return bool(
            self._start_url_entry.get().strip()
            and self._start_description_text().strip()
        )

    def _update_start_generate_state(self, _event: object | None = None) -> None:
        if self._start_busy:
            self._start_generate_btn.configure(state="disabled")
            return
        state = "normal" if self._start_has_inputs() else "disabled"
        self._start_generate_btn.configure(state=state)

    def _start_generate(self) -> None:
        if self._start_busy or not self._start_has_inputs():
            return

        url = self._start_url_entry.get().strip()
        description = self._start_description_text().strip()

        self._start_busy = True
        self._update_start_generate_state()
        self._start_progress_bar.set(0)
        self._start_progress_label.configure(
            text="Saving job posting…", text_color=("gray10", "gray90")
        )

        threading.Thread(
            target=self._start_save_thread,
            args=(description, url),
            daemon=True,
        ).start()

    def _start_save_thread(self, description: str, url: str) -> None:
        try:
            result = save_temporary_job_md(description, url)
            self.after(0, lambda r=result: self._on_start_success(r))
        except ValueError as exc:
            self.after(0, lambda e=exc: self._on_start_failure(e))
        except OSError as exc:
            self.after(0, lambda e=exc: self._on_start_failure(e))

    def _open_start_file_location(self) -> None:
        path = self._start_last_saved_path or get_current_job_md_path()
        if path is None:
            root = job_md_root()
            if root.is_dir():
                path = root
            else:
                messagebox.showinfo(
                    "Open location",
                    "No job file saved yet. Use Generate first, or create a file in Job_MD/.",
                )
                return

        try:
            open_file_location(path)
        except FileNotFoundError as exc:
            messagebox.showerror("Open location", str(exc))
        except OSError as exc:
            messagebox.showerror("Open location", f"Could not open folder:\n{exc}")

    def _on_start_success(self, result: JobMdSaveResult) -> None:
        self._start_busy = False
        self._start_last_saved_path = result.path
        self._last_job_sequence = result.sequence
        url = self._start_url_entry.get().strip()
        try_record_job_start(url, result.sequence)
        self._start_progress_bar.set(1.0)
        self._start_progress_label.configure(
            text=f"Saved {result.path.name} — you can continue on the Resume tab.",
            text_color=("#2FA572", "#2FA572"),
        )
        self._update_start_generate_state()
        self.refresh_application_tracker()

    def _on_start_failure(self, exc: BaseException) -> None:
        self._start_busy = False
        self._start_progress_bar.set(0)
        message = str(exc)
        self._start_progress_label.configure(
            text=f"Save failed: {message}", text_color=("#C42B1C", "#E74C3C")
        )
        self._update_start_generate_state()
        messagebox.showerror("Save failed", message)

    def _on_tab_changed(self) -> None:
        if self.tabs.get() == APPLICATIONS_TAB_NAME:
            self.refresh_application_tracker()

    def _build_applications_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        summary = ctk.CTkFrame(parent, fg_color="transparent")
        summary.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        summary.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._tracker_stat_labels: dict[str, ctk.CTkLabel] = {}
        stat_specs = (
            ("total", "Total applications: 0"),
            ("companies", "Unique companies: 0"),
            ("resume", "With resume: 0"),
            ("cover", "With cover letter: 0"),
        )
        for column, (key, text) in enumerate(stat_specs):
            label = ctk.CTkLabel(summary, text=text, anchor="w")
            label.grid(row=0, column=column, sticky="w", padx=(0, 8))
            self._tracker_stat_labels[key] = label

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="Refresh",
            width=100,
            command=self.refresh_application_tracker,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="Open log folder",
            width=120,
            command=self._open_tracker_log_location,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="Open Excel",
            width=110,
            command=self._open_tracker_excel,
        ).pack(side="left")
        ctk.CTkLabel(
            btn_row,
            text=str(tracker_path()),
            text_color="gray",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))

        table_frame = ctk.CTkFrame(parent)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        col_ids = [spec[0] for spec in _TRACKER_COLUMNS]
        self._tracker_tree = ttk.Treeview(
            table_frame,
            columns=col_ids,
            show="headings",
            selectmode="browse",
        )
        for col_id, heading, width in _TRACKER_COLUMNS:
            self._tracker_tree.heading(col_id, text=heading)
            self._tracker_tree.column(col_id, width=width, minwidth=40, stretch=True)

        tracker_vsb = ctk.CTkScrollbar(
            table_frame, command=self._tracker_tree.yview
        )
        tracker_hsb = ctk.CTkScrollbar(
            table_frame, orientation="horizontal", command=self._tracker_tree.xview
        )
        self._tracker_tree.configure(
            yscrollcommand=tracker_vsb.set, xscrollcommand=tracker_hsb.set
        )
        self._tracker_tree.grid(row=0, column=0, sticky="nsew")
        tracker_vsb.grid(row=0, column=1, sticky="ns")
        tracker_hsb.grid(row=1, column=0, sticky="ew")

    def refresh_application_tracker(self) -> None:
        """Reload tracker stats and table from Excel (read-only)."""
        if not hasattr(self, "_tracker_tree"):
            return
        try:
            stats = application_stats()
            records = load_application_log()
        except OSError as exc:
            messagebox.showerror(
                "Applications", f"Could not read application log:\n{exc}"
            )
            return
        except Exception as exc:
            messagebox.showerror(
                "Applications", f"Could not load application log:\n{exc}"
            )
            return

        self._tracker_stat_labels["total"].configure(
            text=f"Total applications: {stats['total_applications']}"
        )
        self._tracker_stat_labels["companies"].configure(
            text=f"Unique companies: {stats['unique_companies']}"
        )
        self._tracker_stat_labels["resume"].configure(
            text=f"With resume: {stats['with_resume']}"
        )
        self._tracker_stat_labels["cover"].configure(
            text=f"With cover letter: {stats['with_cover_letter']}"
        )

        for item in self._tracker_tree.get_children():
            self._tracker_tree.delete(item)

        for record in sort_application_records(records):
            self._tracker_tree.insert(
                "",
                "end",
                values=(
                    record.date,
                    record.company,
                    record.position,
                    record.website,
                    record.url,
                    record.resume,
                    record.cover_letter,
                ),
            )

    def _open_tracker_log_location(self) -> None:
        path = tracker_path()
        target = path if path.is_file() else path.parent
        if not target.exists():
            messagebox.showinfo(
                "Applications",
                f"Log not found yet:\n{path}\n\nUse Start to create the first entry.",
            )
            return
        try:
            open_file_location(target)
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("Applications", str(exc))

    def _open_tracker_excel(self) -> None:
        path = tracker_path()
        if not path.is_file():
            messagebox.showinfo(
                "Applications",
                f"Excel log not found:\n{path}\n\nUse Start to create the first entry.",
            )
            return
        try:
            open_with_default_app(path)
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("Applications", f"Could not open Excel file:\n{exc}")

    def _ensure_tree_style(self) -> None:
        if self._tree_style_ready:
            return
        tree_style = ttk.Style(self)
        tree_style.configure(
            "Applications.Treeview",
            font=("Segoe UI", APPLICATIONS_PANEL_FONT_SIZE),
            rowheight=APPLICATIONS_PANEL_FONT_SIZE * 2,
        )
        self._tree_style_ready = True

    def _add_collapsible_panel(
        self,
        parent: ctk.CTkFrame,
        *,
        doc_type: str,
        section: str,
        title: str,
        start_row: int,
        boxes: dict[str, ctk.CTkTextbox],
    ) -> int:
        """Add a collapsed-by-default dropdown section; return the next grid row."""
        toggle_btn = ctk.CTkButton(
            parent,
            text=f"▶ {title}",
            anchor="w",
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray80", "gray30"),
            height=28,
            command=lambda dt=doc_type, sec=section: self._toggle_collapsible_panel(
                dt, sec
            ),
        )
        toggle_btn.grid(row=start_row, column=0, sticky="ew", padx=8, pady=(6, 0))

        body_frame = ctk.CTkFrame(parent, fg_color="transparent")
        body_frame.grid(row=start_row + 1, column=0, sticky="ew", padx=8, pady=(0, 4))
        body_frame.grid_columnconfigure(0, weight=1)

        textbox = ctk.CTkTextbox(
            body_frame,
            height=COLLAPSIBLE_PANEL_HEIGHT,
            wrap="word",
            activate_scrollbars=True,
        )
        textbox.grid(row=0, column=0, sticky="nsew")
        boxes[doc_type] = textbox

        body_frame.grid_remove()
        self._collapsible_panels[(doc_type, section)] = {
            "title": title,
            "toggle_btn": toggle_btn,
            "body_frame": body_frame,
            "expanded": False,
        }
        return start_row + 2

    def _toggle_collapsible_panel(self, doc_type: str, section: str) -> None:
        state = self._collapsible_panels[(doc_type, section)]
        title = str(state["title"])
        expanded = not bool(state["expanded"])
        state["expanded"] = expanded
        toggle_btn = state["toggle_btn"]
        body_frame = state["body_frame"]
        assert isinstance(toggle_btn, ctk.CTkButton)
        assert isinstance(body_frame, ctk.CTkFrame)
        arrow = "▼" if expanded else "▶"
        toggle_btn.configure(text=f"{arrow} {title}")
        if expanded:
            body_frame.grid()
        else:
            body_frame.grid_remove()

    def _build_document_tab(self, parent: ctk.CTkFrame, doc_type: str) -> None:
        label = _DOC_TO_VIEW[doc_type]
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(parent)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text=f"{label} JSON:").grid(
            row=0, column=0, padx=(8, 6), pady=6, sticky="w"
        )
        entry = ctk.CTkEntry(
            top,
            placeholder_text=f"Select a {label.lower()} JSON file…",
        )
        entry.grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        self._json_entries[doc_type] = entry

        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=(6, 8), pady=6)
        ctk.CTkButton(
            btn_frame,
            text="Browse…",
            width=90,
            command=lambda dt=doc_type: self.browse_json(dt),
        ).pack(side="left", padx=(0, 6))
        generate_btn = ctk.CTkButton(
            btn_frame,
            text=f"Generate {label.lower()}",
            width=150,
            command=lambda dt=doc_type: self.generate_document(dt),
        )
        generate_btn.pack(side="left")
        self._generate_buttons[doc_type] = generate_btn

        body = ctk.CTkFrame(parent)
        body.grid(row=1, column=0, sticky="nsew", pady=6)
        body.grid_columnconfigure(0, weight=0, minsize=APPLICATIONS_TREE_MINSIZE)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        tree_panel = ctk.CTkFrame(body)
        tree_panel.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        tree_panel.grid_rowconfigure(1, weight=1)
        tree_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tree_panel,
            text="Applications folder",
            anchor="w",
            font=ctk.CTkFont(size=APPLICATIONS_PANEL_FONT_SIZE, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        tree_container = ctk.CTkFrame(tree_panel)
        tree_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self._ensure_tree_style()
        tree = ttk.Treeview(
            tree_container,
            show="tree",
            selectmode="extended",
            style="Applications.Treeview",
        )
        tree_scroll = ctk.CTkScrollbar(tree_container, command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        tree.bind("<Double-1>", self._on_tree_double_click)
        self._trees[doc_type] = tree

        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.grid_columnconfigure(0, weight=1)

        progress_label = ctk.CTkLabel(right, text="", anchor="w", text_color="gray")
        progress_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        self._progress_labels[doc_type] = progress_label

        progress_bar = ctk.CTkProgressBar(right, mode="determinate")
        progress_bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
        progress_bar.set(0)
        self._progress_bars[doc_type] = progress_bar

        panel_row = 2
        panel_row = self._add_collapsible_panel(
            right,
            doc_type=doc_type,
            section="result",
            title="Result",
            start_row=panel_row,
            boxes=self._status_boxes,
        )
        panel_row = self._add_collapsible_panel(
            right,
            doc_type=doc_type,
            section="warnings",
            title="Warnings & errors",
            start_row=panel_row,
            boxes=self._warn_boxes,
        )
        self._add_collapsible_panel(
            right,
            doc_type=doc_type,
            section="trim",
            title="Trim",
            start_row=panel_row,
            boxes=self._trim_boxes,
        )

        bottom = ctk.CTkFrame(parent)
        bottom.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        ctk.CTkButton(bottom, text="Refresh tree", width=110, command=self.refresh_tree).pack(
            side="left", padx=8, pady=8
        )
        ctk.CTkButton(
            bottom,
            text="Validate JSON",
            width=120,
            command=lambda dt=doc_type: self._preflight_document(dt),
        ).pack(side="left", padx=(0, 8), pady=8)
        ctk.CTkButton(
            bottom,
            text="Open",
            width=80,
            command=lambda dt=doc_type: self.open_selected_file(dt),
        ).pack(side="left", padx=(0, 8), pady=8)
        delete_btn = ctk.CTkButton(
            bottom,
            text="Delete",
            width=80,
            command=lambda dt=doc_type: self.delete_selected_file(dt),
        )
        delete_btn.pack(side="left", padx=(0, 8), pady=8)
        self._delete_buttons[doc_type] = delete_btn
        if doc_type == DOC_RESUME:
            ctk.CTkButton(
                bottom,
                text="Open MD location",
                width=130,
                command=self._open_resume_md_location,
            ).pack(side="left", padx=(0, 8), pady=8)
            md_frame = ctk.CTkFrame(bottom, fg_color="transparent")
            md_frame.pack(side="left", padx=(0, 8), pady=8)
            ctk.CTkLabel(md_frame, text="Resume #:").pack(side="left", padx=(0, 4))
            self._resume_md_number_box = ctk.CTkEntry(
                md_frame, width=56, justify="center", state="disabled"
            )
            self._resume_md_number_box.pack(side="left")
            self._update_resume_md_display()
        ctk.CTkLabel(
            bottom,
            text=f"Output: {APPLICATIONS_DIR}",
            text_color="gray",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=8)

    def _resume_md_number_text(self, path: Path | None) -> str:
        if path is None:
            return "—"
        stem = path.stem
        if stem.startswith("resume_"):
            return stem.removeprefix("resume_")
        return path.name

    def _update_resume_md_display(self) -> None:
        if not hasattr(self, "_resume_md_number_box"):
            return
        path = self._resume_last_md_path or get_current_resume_md_path()
        text = self._resume_md_number_text(path)
        self._resume_md_number_box.configure(state="normal")
        self._resume_md_number_box.delete(0, "end")
        self._resume_md_number_box.insert(0, text)
        self._resume_md_number_box.configure(state="disabled")

    def _open_resume_md_location(self) -> None:
        path = self._resume_last_md_path or get_current_resume_md_path()
        if path is None:
            root = resume_md_root()
            if root.is_dir():
                path = root
            else:
                messagebox.showinfo(
                    "Open MD location",
                    "No resume Markdown file yet. Generate a resume first.",
                )
                return

        try:
            open_file_location(path)
        except FileNotFoundError as exc:
            messagebox.showerror("Open MD location", str(exc))
        except OSError as exc:
            messagebox.showerror("Open MD location", f"Could not open folder:\n{exc}")

    def _build_settings_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(
            header,
            text=f"Editing: {DEFAULT_SETTINGS_PATH}",
            text_color="gray",
            anchor="w",
        ).pack(side="left", padx=4)

        scroll = ctk.CTkScrollableFrame(parent)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(1, weight=1)

        self._settings_status = ctk.CTkLabel(
            parent, text="", anchor="w", text_color="gray"
        )
        self._settings_status.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ctk.CTkButton(btn_row, text="Reload", width=100, command=self.reload_settings).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(btn_row, text="Save", width=100, command=self.save_settings).pack(
            side="left"
        )

        self._settings_scroll = scroll
        self.reload_settings()

    def _settings_section(self, parent: ctk.CTkScrollableFrame, title: str, row: int) -> int:
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(12, 6))
        return row + 1

    def _settings_field(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        label: str,
        key: str,
        *,
        kind: str = "text",
    ) -> int:
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 8), pady=4
        )
        if kind == "switch":
            widget: ctk.CTkBaseClass = ctk.CTkSwitch(parent, text="")
        else:
            widget = ctk.CTkEntry(parent)
            widget.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=4)
            self._settings_widgets[key] = widget
            return row + 1

        widget.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=4)
        self._settings_widgets[key] = widget
        return row + 1

    def _settings_compact_number_row(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        label: str,
        key: str,
    ) -> int:
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 8), pady=4
        )
        entry = ctk.CTkEntry(parent, width=SETTINGS_NUMBER_ENTRY_WIDTH)
        entry.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=4)
        self._settings_widgets[key] = entry
        return row + 1

    def _settings_pair_number_row(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        left_label: str,
        left_key: str,
        right_label: str,
        right_key: str,
    ) -> int:
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(
            row=row, column=0, columnspan=2, sticky="w", padx=(16, 16), pady=4
        )

        left_block = ctk.CTkFrame(row_frame, fg_color="transparent")
        left_block.pack(side="left")
        ctk.CTkLabel(left_block, text=left_label, anchor="w").pack(side="left", padx=(0, 6))
        left_entry = ctk.CTkEntry(left_block, width=SETTINGS_NUMBER_ENTRY_WIDTH)
        left_entry.pack(side="left")
        self._settings_widgets[left_key] = left_entry

        right_block = ctk.CTkFrame(row_frame, fg_color="transparent")
        right_block.pack(side="left", padx=(24, 0))
        ctk.CTkLabel(right_block, text=right_label, anchor="w").pack(side="left", padx=(0, 6))
        right_entry = ctk.CTkEntry(right_block, width=SETTINGS_NUMBER_ENTRY_WIDTH)
        right_entry.pack(side="left")
        self._settings_widgets[right_key] = right_entry

        return row + 1

    @staticmethod
    def _bullet_group_section_names(data: dict) -> list[str]:
        """Section prefixes for override rows (trim order first, then existing groups)."""
        names: list[str] = []
        seen: set[str] = set()
        for item in data.get("trim", {}).get("order", []):
            if isinstance(item, dict):
                section = str(item.get("section", "")).strip()
                if section and section not in seen:
                    names.append(section)
                    seen.add(section)
        groups = data.get("bullets", {}).get("groups", {})
        if isinstance(groups, dict):
            for key in sorted(groups):
                if isinstance(key, str) and key.strip() and key not in seen:
                    names.append(key.strip())
                    seen.add(key.strip())
        if not names:
            return list(DEFAULT_BULLET_SECTIONS)
        return names

    def _settings_bullet_group_row(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        prefix: str,
    ) -> int:
        display = prefix.replace("_", " ").title()
        ctk.CTkLabel(parent, text=display, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 8), pady=4
        )
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=4)

        left_block = ctk.CTkFrame(row_frame, fg_color="transparent")
        left_block.pack(side="left")
        ctk.CTkLabel(left_block, text="Max Characters", anchor="w").pack(
            side="left", padx=(0, 6)
        )
        chars_entry = ctk.CTkEntry(left_block, width=SETTINGS_NUMBER_ENTRY_WIDTH)
        chars_entry.pack(side="left")
        self._settings_widgets[f"bullets.groups.{prefix}.max_characters"] = chars_entry

        right_block = ctk.CTkFrame(row_frame, fg_color="transparent")
        right_block.pack(side="left", padx=(16, 0))
        ctk.CTkLabel(right_block, text="Max Count", anchor="w").pack(side="left", padx=(0, 6))
        count_entry = ctk.CTkEntry(right_block, width=SETTINGS_NUMBER_ENTRY_WIDTH)
        count_entry.pack(side="left")
        self._settings_widgets[f"bullets.groups.{prefix}.max_count"] = count_entry

        return row + 1

    def _optional_int(self, raw: str, label: str) -> int | None:
        text = raw.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer") from exc

    def _collect_bullet_groups_from_form(
        self,
        default_characters: int,
        default_count: int,
    ) -> dict:
        groups: dict = {}
        for prefix in self._bullet_group_sections:
            chars_key = f"bullets.groups.{prefix}.max_characters"
            count_key = f"bullets.groups.{prefix}.max_count"
            chars_raw = self._entry_text(chars_key, self._settings_widgets[chars_key])
            count_raw = self._entry_text(count_key, self._settings_widgets[count_key])
            if not chars_raw and not count_raw:
                continue
            max_characters = self._optional_int(chars_raw, f"{prefix} max characters")
            max_count = self._optional_int(count_raw, f"{prefix} max count")
            groups[prefix] = {
                "max_characters": (
                    max_characters if max_characters is not None else default_characters
                ),
                "max_count": max_count if max_count is not None else default_count,
            }
        return groups

    @staticmethod
    def _sections_from_trim_order(order: list) -> list[str]:
        sections: list[str] = []
        for item in order:
            if isinstance(item, dict):
                sections.append(str(item.get("section", "")).strip())
        while len(sections) < TRIM_ORDER_SLOTS:
            sections.append("")
        return sections[:TRIM_ORDER_SLOTS]

    def _settings_trim_priority_row(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        priority: int,
    ) -> int:
        label = f"Priority {priority}"
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 8), pady=4
        )
        placeholder = "goose" if priority == TRIM_ORDER_SLOTS else ""
        entry = ctk.CTkEntry(
            parent, width=TRIM_PRIORITY_ENTRY_WIDTH, placeholder_text=placeholder
        )
        entry.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=4)
        self._settings_widgets[f"trim.order.priority.{priority}"] = entry
        return row + 1

    def _collect_trim_order_from_form(self) -> list[dict]:
        steps: list[dict] = []
        for priority in range(1, TRIM_ORDER_SLOTS + 1):
            key = f"trim.order.priority.{priority}"
            section = self._entry_text(key, self._settings_widgets[key])
            if not section:
                raise ValueError(f"Priority {priority} must have a section name")
            remove = (
                self._trim_remove_types[priority - 1]
                if priority - 1 < len(self._trim_remove_types)
                else TRIM_REMOVE_DEFAULT
            )
            steps.append({"section": section, "remove": remove})
        return steps

    def _settings_template_row(
        self,
        parent: ctk.CTkScrollableFrame,
        row: int,
        name: str,
    ) -> int:
        """One template row: label | switch, Browse, arrow; path hidden until expanded."""
        key_enabled = f"templates.{name}.enabled"
        key_path = f"templates.{name}.path"
        label_text = name.replace("_", " ").title()

        ctk.CTkLabel(parent, text=label_text, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(16, 8), pady=4
        )

        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=4)

        switch = ctk.CTkSwitch(controls, text="")
        switch.pack(side="left")
        self._settings_widgets[key_enabled] = switch

        ctk.CTkButton(
            controls,
            text="Browse",
            width=72,
            command=lambda k=key_path: self._browse_template_path(k),
        ).pack(side="left", padx=(8, 0))

        arrow_btn = ctk.CTkButton(
            controls,
            text="▶",
            width=28,
            command=lambda k=key_path: self._toggle_template_path(k),
        )
        arrow_btn.pack(side="left", padx=(4, 0))
        self._template_path_arrows[key_path] = arrow_btn

        path_row = row + 1
        path_frame = ctk.CTkFrame(parent, fg_color="transparent")
        path_frame.grid_columnconfigure(0, weight=1)
        path_frame.grid(
            row=path_row,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(32, 16),
            pady=(0, 4),
        )
        path_frame.grid_remove()

        entry = ctk.CTkEntry(path_frame, placeholder_text="Template path…")
        entry.grid(row=0, column=0, sticky="ew")
        self._settings_widgets[key_path] = entry
        self._template_path_frames[key_path] = path_frame

        return path_row + 1

    def _toggle_template_path(self, key: str) -> None:
        frame = self._template_path_frames.get(key)
        arrow = self._template_path_arrows.get(key)
        if frame is None or arrow is None:
            return
        if frame.winfo_ismapped():
            frame.grid_remove()
            arrow.configure(text="▶")
        else:
            frame.grid()
            arrow.configure(text="▼")

    def _browse_template_path(self, key: str) -> None:
        entry = self._settings_widgets[key]
        if not isinstance(entry, ctk.CTkEntry):
            return

        current = entry.get().strip()
        initialdir = MAIN_ROOT / "config" / "templates"
        if current and current.lower() != "null":
            candidate = (MAIN_ROOT / current).resolve()
            if candidate.is_file():
                initialdir = candidate.parent
            elif candidate.parent.is_dir():
                initialdir = candidate.parent

        path = ctk.filedialog.askopenfilename(
            title="Select template",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
            initialdir=str(initialdir),
        )
        if not path:
            return

        picked = Path(path).resolve()
        try:
            display = picked.relative_to(MAIN_ROOT).as_posix()
        except ValueError:
            display = str(picked)

        entry.delete(0, "end")
        entry.insert(0, display)

    def _clear_settings_form(self) -> None:
        for widget in self._settings_scroll.winfo_children():
            widget.destroy()
        self._settings_widgets.clear()
        self._template_path_frames.clear()
        self._template_path_arrows.clear()

    def reload_settings(self) -> None:
        """Load settings via config and fill the Settings tab fields."""
        try:
            cfg = load_config(self._settings_path)
            self._settings_path = cfg.settings_path
            data = config_to_dict(cfg)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            self._settings_status.configure(
                text=f"Could not load settings: {exc}", text_color="#E74C3C"
            )
            return

        self._clear_settings_form()
        scroll = self._settings_scroll
        row = 0

        templates = data.get("templates", {})
        row = self._settings_section(scroll, "Templates", row)
        for name in ("resume", "cover_letter"):
            tpl = templates.get(name, {})
            row = self._settings_template_row(scroll, row, name)
            enabled_key = f"templates.{name}.enabled"
            if tpl.get("enabled"):
                self._settings_widgets[enabled_key].select()
            else:
                self._settings_widgets[enabled_key].deselect()
            path_val = tpl.get("path")
            entry = self._settings_widgets[f"templates.{name}.path"]
            entry.delete(0, "end")
            entry.insert(0, "" if path_val is None else str(path_val))

        bullets = data.get("bullets", {})
        self._bullet_group_sections = self._bullet_group_section_names(data)
        row = self._settings_section(scroll, "Bullet Points", row)
        row = self._settings_pair_number_row(
            scroll,
            row,
            "Max Characters",
            "bullets.default_max_characters",
            "Max Count",
            "bullets.default_max_count",
        )
        self._settings_widgets["bullets.default_max_characters"].insert(
            0, str(bullets.get("default_max_characters", ""))
        )
        self._settings_widgets["bullets.default_max_count"].insert(
            0, str(bullets.get("default_max_count", ""))
        )
        row = self._settings_section(scroll, "Section Overrides", row)
        ctk.CTkLabel(
            scroll,
            text="Leave blank to use defaults above.",
            text_color="gray",
            anchor="w",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=(16, 16), pady=(0, 4))
        row += 1
        groups = bullets.get("groups", {})
        if not isinstance(groups, dict):
            groups = {}
        for prefix in self._bullet_group_sections:
            row = self._settings_bullet_group_row(scroll, row, prefix)
            group_cfg = groups.get(prefix, {})
            if isinstance(group_cfg, dict):
                chars_entry = self._settings_widgets[
                    f"bullets.groups.{prefix}.max_characters"
                ]
                count_entry = self._settings_widgets[f"bullets.groups.{prefix}.max_count"]
                if group_cfg.get("max_characters") is not None:
                    chars_entry.insert(0, str(group_cfg["max_characters"]))
                if group_cfg.get("max_count") is not None:
                    count_entry.insert(0, str(group_cfg["max_count"]))

        pages = data.get("pages", {})
        self._retained_default_max_pages = int(pages.get("default_max_pages", 1))
        row = self._settings_section(scroll, "Pages", row)
        row = self._settings_pair_number_row(
            scroll,
            row,
            "Resume — Max Pages",
            "pages.resume.max_pages",
            "Cover Letter — Max Pages",
            "pages.cover_letter.max_pages",
        )
        self._settings_widgets["pages.resume.max_pages"].insert(
            0, str(pages.get("resume", {}).get("max_pages", ""))
        )
        self._settings_widgets["pages.cover_letter.max_pages"].insert(
            0, str(pages.get("cover_letter", {}).get("max_pages", ""))
        )
        for name in ("resume", "cover_letter"):
            page_cfg = pages.get(name, {})
            display_name = name.replace("_", " ").title()
            row = self._settings_field(
                scroll,
                row,
                f"{display_name} — Check Enable",
                f"pages.{name}.check_enabled",
                kind="switch",
            )
            switch = self._settings_widgets[f"pages.{name}.check_enabled"]
            if page_cfg.get("check_enabled"):
                switch.select()
            else:
                switch.deselect()

        trim = data.get("trim", {})
        row = self._settings_section(scroll, "Trim (page over limit)", row)
        row = self._settings_field(
            scroll, row, "enabled", "trim.enabled", kind="switch"
        )
        trim_switch = self._settings_widgets["trim.enabled"]
        if trim.get("enabled"):
            trim_switch.select()
        else:
            trim_switch.deselect()
        row = self._settings_field(scroll, row, "max_attempts", "trim.max_attempts")
        self._settings_widgets["trim.max_attempts"].insert(
            0, str(trim.get("max_attempts", ""))
        )
        order = trim.get("order", [])
        remove_types: list[str] = []
        for item in order:
            if isinstance(item, dict):
                remove_types.append(str(item.get("remove", TRIM_REMOVE_DEFAULT)).strip())
        while len(remove_types) < TRIM_ORDER_SLOTS:
            remove_types.append(TRIM_REMOVE_DEFAULT)
        self._trim_remove_types = remove_types[:TRIM_ORDER_SLOTS]

        row = self._settings_section(scroll, "Order", row)
        sections = self._sections_from_trim_order(order)
        for priority in range(1, TRIM_ORDER_SLOTS + 1):
            row = self._settings_trim_priority_row(scroll, row, priority)
            entry = self._settings_widgets[f"trim.order.priority.{priority}"]
            entry.insert(0, sections[priority - 1])

        self._settings_status.configure(
            text="Loaded from settings.json", text_color="gray"
        )

    @staticmethod
    def _entry_text(key: str, widget: ctk.CTkBaseClass) -> str:
        if isinstance(widget, ctk.CTkTextbox):
            return widget.get("1.0", "end").strip()
        if isinstance(widget, ctk.CTkEntry):
            return widget.get().strip()
        raise TypeError(f"Unsupported widget for {key}")

    @staticmethod
    def _switch_value(widget: ctk.CTkBaseClass) -> bool:
        return bool(widget.get())  # type: ignore[union-attr]

    @staticmethod
    def _path_value(raw: str) -> str | None:
        text = raw.strip()
        if not text or text.lower() == "null":
            return None
        return text

    def _collect_settings_from_form(self) -> dict:
        trim_order = self._collect_trim_order_from_form()

        def int_field(key: str) -> int:
            raw = self._entry_text(key, self._settings_widgets[key])
            if not raw:
                raise ValueError(f"{key} is required")
            try:
                return int(raw)
            except ValueError as exc:
                raise ValueError(f"{key} must be an integer") from exc

        default_characters = int_field("bullets.default_max_characters")
        default_count = int_field("bullets.default_max_count")
        groups = self._collect_bullet_groups_from_form(
            default_characters, default_count
        )

        return {
            "templates": {
                "resume": {
                    "enabled": self._switch_value(
                        self._settings_widgets["templates.resume.enabled"]
                    ),
                    "path": self._path_value(
                        self._entry_text(
                            "templates.resume.path",
                            self._settings_widgets["templates.resume.path"],
                        )
                    ),
                },
                "cover_letter": {
                    "enabled": self._switch_value(
                        self._settings_widgets["templates.cover_letter.enabled"]
                    ),
                    "path": self._path_value(
                        self._entry_text(
                            "templates.cover_letter.path",
                            self._settings_widgets["templates.cover_letter.path"],
                        )
                    ),
                },
            },
            "bullets": {
                "default_max_characters": default_characters,
                "default_max_count": default_count,
                "groups": groups,
            },
            "pages": {
                "default_max_pages": self._retained_default_max_pages,
                "resume": {
                    "max_pages": int_field("pages.resume.max_pages"),
                    "check_enabled": self._switch_value(
                        self._settings_widgets["pages.resume.check_enabled"]
                    ),
                },
                "cover_letter": {
                    "max_pages": int_field("pages.cover_letter.max_pages"),
                    "check_enabled": self._switch_value(
                        self._settings_widgets["pages.cover_letter.check_enabled"]
                    ),
                },
            },
            "trim": {
                "enabled": self._switch_value(self._settings_widgets["trim.enabled"]),
                "max_attempts": int_field("trim.max_attempts"),
                "order": trim_order,
            },
        }

    def save_settings(self) -> None:
        """Validate form values through config and write settings.json."""
        try:
            data = self._collect_settings_from_form()
            cfg = config_from_dict(data)
            save_config(cfg, self._settings_path)
            self._settings_path = cfg.settings_path
        except ValueError as exc:
            self._settings_status.configure(
                text=str(exc), text_color="#E74C3C"
            )
            messagebox.showerror("Settings", str(exc))
            return
        except OSError as exc:
            self._settings_status.configure(
                text=f"Could not save: {exc}", text_color="#E74C3C"
            )
            messagebox.showerror("Settings", f"Could not save settings:\n{exc}")
            return

        self._settings_status.configure(
            text="Saved to settings.json", text_color="#2ECC71"
        )
        messagebox.showinfo("Settings", "Settings saved to settings.json.")

    def _set_textbox(self, box: ctk.CTkTextbox, content: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        if content:
            box.insert("1.0", content)
        box.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in self._generate_buttons.values():
            button.configure(state=state)
        for button in self._delete_buttons.values():
            button.configure(state=state)

    def _clear_status_box(self, doc_type: str | None = None) -> None:
        box = self._status_boxes[doc_type or self._active_generation_type]
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.configure(state="disabled")

    def _append_status_text(self, text: str, doc_type: str | None = None) -> None:
        if not text:
            return
        box = self._status_boxes[doc_type or self._active_generation_type]
        box.configure(state="normal")
        box.insert("end", text)
        if not text.endswith("\n"):
            box.insert("end", "\n")
        box.see("end")
        box.configure(state="disabled")

    def _append_trim_text(self, text: str, doc_type: str | None = None) -> None:
        if not text:
            return
        box = self._trim_boxes[doc_type or self._active_generation_type]
        box.configure(state="normal")
        box.insert("end", text)
        if not text.endswith("\n"):
            box.insert("end", "\n")
        box.see("end")
        box.configure(state="disabled")

    def _is_trim_progress(self, event: PipelineProgress) -> bool:
        message = event.message.strip()
        return event.phase == PHASE_TRIM or message.startswith("Trim:")

    def _already_streamed(self, text: str) -> bool:
        needle = text.strip()
        if not needle:
            return True
        for msg in self._streamed_messages:
            if needle in msg or msg in needle:
                return True
        return False

    def _handle_progress_event(self, event: PipelineProgress) -> None:
        doc_type = self._active_generation_type
        trim_event = self._is_trim_progress(event)
        if trim_event:
            self._append_trim_text(event.message, doc_type)
        else:
            self._append_status_text(event.message, doc_type)
        self._streamed_messages.add(event.message)
        if event.phase in (PHASE_FAILED, CL_PHASE_FAILED):
            self._saw_failed_phase = True

        if event.detail:
            detail = event.detail.strip()
            if (
                detail
                and detail != event.message.strip()
                and detail not in event.message
                and not self._already_streamed(detail)
            ):
                if trim_event:
                    self._append_trim_text(detail, doc_type)
                else:
                    self._append_status_text(detail, doc_type)
                self._streamed_messages.add(detail)

        total = max(event.total_steps, 1)
        fraction = min(1.0, max(0.0, event.step / total))
        self._progress_bars[doc_type].set(fraction)
        self._progress_labels[doc_type].configure(text=event.message)

    def _drain_progress_queue(self) -> None:
        if self._progress_queue is None:
            return
        while True:
            try:
                event = self._progress_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_progress_event(event)

    def _poll_progress_queue(self) -> None:
        if not self._busy or self._progress_queue is None:
            return
        self._drain_progress_queue()
        self.after(50, self._poll_progress_queue)

    def browse_json(self, doc_type: str) -> None:
        path = ctk.filedialog.askopenfilename(
            title=f"Select {_DOC_TO_VIEW[doc_type].lower()} JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(PROJECT_ROOT),
        )
        if not path:
            return
        resolved = Path(path).resolve()
        entry = self._json_entries[doc_type]
        entry.delete(0, "end")
        entry.insert(0, str(resolved))
        self._preflight_document(doc_type)

    def _current_json_path(self, doc_type: str) -> Path | None:
        raw = self._json_entries[doc_type].get().strip()
        if not raw:
            return None
        return Path(raw).resolve()

    def _preflight_document(self, doc_type: str) -> None:
        warn_box = self._warn_boxes[doc_type]
        json_path = self._current_json_path(doc_type)
        if json_path is None:
            self._set_textbox(
                warn_box, f"Enter or browse to a {_DOC_TO_VIEW[doc_type].lower()} JSON file first."
            )
            return
        if not json_path.is_file():
            self._set_textbox(warn_box, f"JSON file not found: {json_path}")
            return

        try:
            if doc_type == DOC_RESUME:
                result = validate_json_file(json_path)
            else:
                result = validate_cover_letter_json_file(json_path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            self._set_textbox(warn_box, f"Config error: {exc}")
            return

        label = _DOC_TO_VIEW[doc_type]
        if result.valid:
            self._set_textbox(warn_box, f"{label} JSON validation: OK")
        else:
            lines = [f"{label} JSON validation failed:"]
            lines.extend(f"  - {m}" for m in result.messages())
            self._set_textbox(warn_box, "\n".join(lines))

    def refresh_tree(self, highlight: Path | None = None) -> None:
        for tree in self._trees.values():
            populate_applications_tree(tree, highlight=highlight)

    def _on_tree_double_click(self, event: object) -> None:
        widget = getattr(event, "widget", None)
        if widget is None:
            return
        for doc_type, tree in self._trees.items():
            if widget == tree:
                self.open_selected_file(doc_type)
                return

    def open_selected_file(self, doc_type: str) -> None:
        """Open the selected .docx or .pdf with the system default app."""
        tree = self._trees[doc_type]
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(
                "Open file",
                "Select a .docx or .pdf in the Applications tree, then click Open.",
            )
            return

        file_path = path_for_tree_item(tree, selection[0])
        if file_path is None:
            messagebox.showinfo(
                "Open file",
                "Select a resume file (.docx or .pdf), not a folder.",
            )
            return

        if file_path.suffix.lower() not in RESUME_EXTENSIONS:
            messagebox.showinfo(
                "Open file",
                "Only .docx and .pdf files can be opened from here.",
            )
            return

        try:
            open_with_default_app(file_path)
        except FileNotFoundError as exc:
            messagebox.showerror("Open file", str(exc))
        except OSError as exc:
            messagebox.showerror("Open file", f"Could not open file:\n{exc}")

    def delete_selected_file(self, doc_type: str) -> None:
        """Delete selected application files and/or position folders."""
        if self._busy:
            return

        tree = self._trees[doc_type]
        targets, skip_info = resolve_tree_selection(tree)
        if not targets:
            messagebox.showinfo("Delete", skip_info or "Nothing to delete.")
            return

        if not messagebox.askyesno("Delete", delete_plan_confirm_message(targets)):
            return

        status_lines: list[str] = []
        errors: list[str] = []
        company_dirs_to_clean: set[Path] = set()

        folder_targets = [
            path for role, path in targets if role == TREE_ROLE_POSITION
        ]
        file_targets = [path for role, path in targets if role == TREE_ROLE_FILE]

        for folder in folder_targets:
            company_dirs_to_clean.add(folder.parent.resolve())

        for folder in folder_targets:
            try:
                result = delete_position_folder(folder)
            except FileNotFoundError:
                status_lines.append(f"Folder already removed: {folder.name}")
                continue
            except ValueError as exc:
                errors.append(str(exc))
                continue

            if result.errors:
                errors.extend(result.errors)
            if result.deleted:
                status_lines.append(
                    f"Deleted position folder: {folder.parent.name} / {folder.name}"
                )
            else:
                status_lines.append(f"Folder already empty: {folder.name}")

        for file_path in file_targets:
            try:
                result = delete_application_file(
                    file_path,
                    include_paired_pdf_docx=DELETE_INCLUDE_PAIRED_PDF_DOCX,
                )
            except FileNotFoundError:
                status_lines.append(f"Already deleted: {file_path.name}")
                company_dirs_to_clean.add(file_path.parent.parent.resolve())
                continue
            except ValueError as exc:
                errors.append(str(exc))
                continue

            if result.errors:
                errors.extend(result.errors)
            for deleted_path in result.deleted:
                status_lines.append(f"Deleted: {deleted_path}")
                company_dirs_to_clean.add(deleted_path.parent.parent.resolve())

        for company_dir in company_dirs_to_clean:
            try_remove_empty_company_dir(company_dir)

        self.refresh_tree()

        if errors:
            messagebox.showerror("Delete", "\n".join(errors))

        if status_lines:
            for line in status_lines:
                self._append_status_text(line, doc_type)
        elif not errors:
            messagebox.showinfo("Delete", "Nothing was deleted.")

        if skip_info and status_lines:
            self._append_status_text(skip_info, doc_type)

    def generate_document(self, doc_type: str) -> None:
        if self._busy:
            return

        json_path = self._current_json_path(doc_type)
        label = _DOC_TO_VIEW[doc_type]
        if json_path is None:
            messagebox.showwarning("No JSON", f"Choose a {label.lower()} JSON file first.")
            return
        if not json_path.is_file():
            messagebox.showerror("File not found", f"JSON file not found:\n{json_path}")
            return

        self._active_generation_type = doc_type
        self._progress_queue = queue.Queue()
        self._streamed_messages = set()
        self._saw_failed_phase = False
        self._set_busy(True)
        self._clear_status_box(doc_type)
        self._append_status_text("Starting generation…", doc_type)
        self._set_textbox(self._warn_boxes[doc_type], "")
        self._set_textbox(self._trim_boxes[doc_type], "")
        self._progress_bars[doc_type].set(0)
        self._progress_labels[doc_type].configure(
            text=f"Starting {label.lower()} generation…"
        )
        self._poll_progress_queue()

        threading.Thread(
            target=self._run_pipeline_thread,
            args=(json_path, doc_type),
            daemon=True,
        ).start()

    def _run_pipeline_thread(self, json_path: Path, doc_type: str) -> None:
        def on_progress(event: PipelineProgress) -> None:
            if self._progress_queue is not None:
                self._progress_queue.put(event)

        try:
            if doc_type == DOC_RESUME:
                result = run_pipeline(
                    json_path,
                    on_progress=on_progress,
                    job_sequence=self._last_job_sequence,
                )
                self.after(0, lambda r=result: self._on_success(r, DOC_RESUME))
            else:
                result = run_cover_letter_pipeline(
                    json_path,
                    on_progress=on_progress,
                    job_sequence=self._last_job_sequence,
                )
                self.after(0, lambda r=result: self._on_success(r, DOC_COVER_LETTER))
        except (FileNotFoundError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            self.after(0, lambda e=exc, dt=doc_type: self._on_failure(e, dt))
        except OSError as exc:
            self.after(0, lambda e=exc, dt=doc_type: self._on_failure(e, dt))
        except AttributeError as exc:
            self.after(0, lambda e=exc, dt=doc_type: self._on_failure(e, dt))
        except Exception as exc:
            self.after(0, lambda e=exc, dt=doc_type: self._on_failure(e, dt))

    def _on_success(
        self,
        result: PipelineResult | CoverLetterPipelineResult,
        doc_type: str,
    ) -> None:
        self._drain_progress_queue()
        self._set_busy(False)
        self._progress_bars[doc_type].set(1.0)
        label = _DOC_TO_VIEW[doc_type]
        self._progress_labels[doc_type].configure(
            text=f"{label} run finished successfully."
        )

        success_line = (
            "Resume generated successfully."
            if doc_type == DOC_RESUME
            else "Cover letter generated successfully."
        )
        self._append_status_text("---", doc_type)
        self._append_status_text(success_line, doc_type)

        path_lines = [
            f"Position folder: {result.position_dir}",
            f"DOCX: {result.docx_path}",
            f"PDF: {result.pdf_path}",
        ]
        for line in path_lines:
            if not self._already_streamed(line):
                self._append_status_text(line, doc_type)

        doc_label = label.lower()
        page_lines, page_warnings, trim_lines = format_page_lines(
            result, document_label=doc_label
        )
        for line in page_lines:
            if not self._already_streamed(line):
                self._append_status_text(line, doc_type)

        if result.log_path and not self._already_streamed(str(result.log_path)):
            self._append_status_text(f"Log: {result.log_path}", doc_type)

        warn_lines = list(page_warnings) or ["(no warnings)"]
        self._set_textbox(self._warn_boxes[doc_type], "\n".join(warn_lines))

        trim_text = "\n".join(trim_lines) if trim_lines else "(nothing trimmed)"
        self._set_textbox(self._trim_boxes[doc_type], trim_text)

        self.refresh_tree(highlight=result.position_dir)

        if doc_type == DOC_RESUME:
            md_path = get_current_resume_md_path()
            if md_path is not None:
                self._resume_last_md_path = md_path
            self._update_resume_md_display()

        if result.over_page_limit:
            messagebox.showwarning(
                "Page limit exceeded",
                f"The {label.lower()} PDF has {result.page_count} page(s) "
                f"(limit {result.max_pages}).\n\n"
                "Files were still created. See Warnings for details.",
            )

        self.refresh_application_tracker()

    def _on_failure(self, exc: BaseException, doc_type: str) -> None:
        self._drain_progress_queue()
        self._set_busy(False)
        self._progress_bars[doc_type].set(0)
        label = _DOC_TO_VIEW[doc_type]
        message = str(exc)
        if not self._saw_failed_phase:
            self._append_status_text("Generation failed.", doc_type)
        self._progress_labels[doc_type].configure(text=f"{label} generation failed.")
        self._set_textbox(self._warn_boxes[doc_type], message)
        messagebox.showerror(f"{label} generation failed", message)


def main() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = ResumeGui()
    app.mainloop()


if __name__ == "__main__":
    main()
