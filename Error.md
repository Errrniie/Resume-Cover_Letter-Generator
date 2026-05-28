# Error catalog (current behavior)

Reference for every failure and warning the resume pipeline can produce **as of today**.  
Use this when wiring the GUI and when we add stable error codes and user-facing messages later.

**Entry point:** `Main.run_pipeline()` (`Main.py`)

---

## Not an error: page limit flag

| Field | Type | Meaning |
|-------|------|---------|
| `PipelineResult.over_page_limit` | `bool` | `true` when the generated PDF has more pages than the config limit |
| `PipelineResult.page_check_skipped` | `bool` | `true` when page checking is disabled in `config/settings.json` |

- A run can **succeed** with `over_page_limit: true`.
- When over limit and `trim.enabled` is true in settings, `Main._trim_for_page_limit()` removes bullets per `trim.order` and regenerates docx/pdf until within limit or attempts are exhausted.
- Page-check problems are printed to stderr and written to the run log file; they do **not** stop `run_pipeline()` today.

---

## Pipeline order

1. Load config  
2. Load JSON (file or dict)  
3. Configure file logging (`Logs/{company}/Resume_{Company}_{Position}_{YYYY-MM-DD}.log`)  
4. Validate metadata (`company`, `position` — non-empty after trim)  
5. Validate bullets (config rules)  
6. Write resume snapshot Markdown (`Resume_MD/resume_NNN.md`; non-fatal if write fails)  
7. Create application folders  
8. Build output `.docx` path  
9. Resolve resume template  
10. Parse resume data  
11. Fill resume (`.docx`)  
12. Convert to PDF  
13. Trim for page limit (when enabled and over limit)  
14. Check PDF page count (non-fatal)

---

## 1. Config — `config.Loader.load_config()`

**Stops pipeline.** Exceptions: `FileNotFoundError`, `ValueError`, `json.JSONDecodeError`

| # | Condition | Exception | Typical message shape |
|---|-----------|-----------|------------------------|
| 1.1 | Settings file missing | `FileNotFoundError` | `Settings file not found: {path}` |
| 1.2 | Settings file is not valid JSON | `json.JSONDecodeError` | Parser detail from `json` |
| 1.3 | Settings root is not a JSON object | `ValueError` | `Settings root must be a JSON object` |
| 1.4 | `templates` is not an object | `ValueError` | `"templates" must be an object` |
| 1.5 | `templates.{name}` is not an object | `ValueError` | `templates.{name} must be an object` |
| 1.6 | `templates.{name}.enabled` is not boolean | `ValueError` | `templates.{name}.enabled must be true or false` |
| 1.7 | `templates.{name}.path` invalid (non-string, empty when set) | `ValueError` | `templates.{name}.path must be a non-empty string or null` |
| 1.8 | Template enabled but `path` is null | `ValueError` | `templates.{name} is enabled but path is not set` |
| 1.9 | `bullets` is not an object | `ValueError` | `"bullets" must be an object` |
| 1.10 | `bullets.default_max_characters` invalid | `ValueError` | Must be integer ≥ 1 |
| 1.11 | `bullets.default_max_count` invalid | `ValueError` | Must be integer ≥ 1 |
| 1.12 | `bullets.groups` is not an object | `ValueError` | `"bullets.groups" must be an object` |
| 1.13 | `bullets.groups` key empty | `ValueError` | `bullets.groups keys must be non-empty strings` |
| 1.14 | `bullets.groups.{prefix}` not an object / missing limits | `ValueError` | Group must be object; must include `max_characters` / `max_count` |
| 1.15 | `pages` is not an object | `ValueError` | `"pages" must be an object` |
| 1.16 | `pages.default_max_pages` invalid | `ValueError` | Must be integer ≥ 1 |
| 1.17 | `pages.{name}` not an object (extra keys) | `ValueError` | `pages.{name} must be an object` |
| 1.18 | `pages.{name}.check_enabled` not boolean | `ValueError` | `pages.{name}.check_enabled must be true or false` |
| 1.19 | `pages.{name}.max_pages` invalid | `ValueError` | Must be integer ≥ 1 |
| 1.20 | `resolve_template_path()` when path is null | `ValueError` | `Template "{name}" has no path configured` |

**Source:** `config/Loader.py`

---

## 2. JSON input — `Main.load_json_input()`

**Stops pipeline** when input is a **file path**. Dict input skips file read errors (2.1–2.2).

| # | Condition | Exception | Typical message shape |
|---|-----------|-----------|------------------------|
| 2.1 | JSON file missing or unreadable | `OSError` / `PermissionError` | OS error (not caught by `Main` today) |
| 2.2 | JSON file is not valid JSON | `json.JSONDecodeError` | Parser detail |
| 2.3 | JSON root is not an object | `ValueError` | `JSON root must be an object` |

**Source:** `Main.py`

---

## 3. Metadata validation — `config.Metadata_Validator.validate_metadata()`

**Stops pipeline** (before bullet validation). `Main` raises `ValueError` with prefix `JSON validation failed:` and one line per issue (same pattern as bullet validation).

| # | Condition | Issue field | Typical message shape |
|---|-----------|-------------|------------------------|
| 3.1 | `company` missing from JSON | `company` | `ERROR company: required but missing` |
| 3.2 | `company` empty or whitespace only | `company` | `ERROR company: required but missing or empty` |
| 3.3 | `position` missing | `position` | `ERROR position: required but missing` |
| 3.4 | `position` empty or whitespace only | `position` | `ERROR position: required but missing or empty` |

**Combined preflight:** `config.Validator.validate_resume_json()` runs metadata then bullets and returns all issues. `Main.run_pipeline()` fails fast on metadata only (bullets are not checked if metadata fails).

**GUI:** “Validate JSON” calls `validate_json_file()` → `validate_resume_json()`.

**Source:** `config/Metadata_Validator.py`, `config/Validator.py`

**Note:** Required fields are hardcoded in `REQUIRED_METADATA_FIELDS` today; they may move to `settings.json` per resume type later.

---

## 4. Bullet validation — `config.Validator.validate_data()`

**Stops pipeline.** `Main` raises `ValueError` with prefix `JSON validation failed:` and one line per issue.

| # | Condition | Issue field | Typical message shape |
|---|-----------|-------------|------------------------|
| 4.1 | `{prefix}_bullets` is not an array | `json` | `"{key}" must be an array of strings` |
| 4.2 | Too many bullets in a group | `{prefix}_bullets` | `{n} bullets (max {max})` |
| 4.3 | Bullet text too long | `{prefix}_bullets[{index}]` | `{length} characters (max {max})` |

**Source:** `config/Validator.py`, `config/Issues.py` (`ValidationIssue.format()` → `{field}: {message}`)

**Note:** `validate_json_file()` also reports file-not-found and invalid JSON (2.x), but `Main` uses `validate_data()` after its own load.

---

## 5. Application folders — `Modules.Application_Path`

**Stops pipeline.** Exception: `ValueError`

| # | Condition | Typical message |
|---|-----------|-----------------|
| 5.1 | Missing or empty `company` | `JSON must include non-empty "company"` |
| 5.2 | Missing or empty `position` | `JSON must include non-empty "position"` |

**May stop pipeline (uncaught by `Main`):**

| # | Condition | Exception |
|---|-----------|-----------|
| 5.3 | Cannot create `Applications/` or subfolders | `OSError`, `PermissionError` |

**Source:** `Modules/Application_Path.py`

---

## 6. Output filename — `Main.unique_resume_docx_path()`

**Stops pipeline.**

| # | Condition | Exception | Typical message |
|---|-----------|-----------|-----------------|
| 6.1 | Missing `company` or `position` for naming | `ValueError` | `JSON must include non-empty "company" and "position" for output naming` |
| 6.2 | Base name exists; `_2`…`_999` all taken | `RuntimeError` | `Could not find unused filename for {filename}` |

**Source:** `Main.py`

---

## 7. Resume template — `Main.resume_template_path()`

**Stops pipeline.**

| # | Condition | Exception | Typical message |
|---|-----------|-----------|-----------------|
| 7.1 | Resume template disabled or no path in settings | `ValueError` | `Resume template is not enabled or has no path in settings.json` |
| 7.2 | Template file does not exist on disk | `FileNotFoundError` | `Resume template not found: {path}` |

**Source:** `Main.py`, `config/Loader.resolve_template_path()`

---

## 8. Parse resume data — `Modules.Fill_Resume.parse_resume_data()`

**Stops pipeline.** Runs after bullet validation; some shape errors are only caught here.

| # | Condition | Typical message |
|---|-----------|-----------------|
| 8.1 | Root not a dict (defensive) | `JSON root must be an object, got {type}` |
| 8.2 | `skills` is not an array | `"skills" must be an array of category objects` |
| 8.3 | `{key}_bullets` is not an array | `"{key}" must be an array of strings` |
| 8.4 | Skills entry is not an object | `Each skills entry must be an object with "category" and "skills"` |
| 8.5 | Skills entry’s `skills` is not an array | `"skills" must be an array of strings` |

**Source:** `Modules/Fill_Resume.py`

---

## 9. Fill resume — `Modules.Fill_Resume.fill_resume()`

**Stops pipeline** (explicit raises).

| # | Condition | Exception | Typical message |
|---|-----------|-----------|-----------------|
| 9.1 | Neither `json_path` nor `data` provided | `ValueError` | `fill_resume requires json_path or data` |
| 9.2 | `json_path` file missing (when no `data`) | `FileNotFoundError` | `JSON file not found: {path}` |
| 9.3 | Template file missing | `FileNotFoundError` | `Template not found: {path}` |
| 9.4 | `output_path` is not `.docx` | `ValueError` | `Output path must be a .docx file: {path}` |

**May stop pipeline (uncaught by `Main`):**

| # | Condition | Exception |
|---|-----------|-----------|
| 9.5 | Corrupt or invalid `.docx` template | `python-docx` / zip / XML errors |
| 9.6 | Cannot copy template or save output | `OSError`, `PermissionError` |
| 9.7 | Disk full | `OSError` |

**Source:** `Modules/Fill_Resume.py`

---

## 10. PDF conversion — `Modules.Pdf_Engine.convert_docx_to_pdf()`

**Stops pipeline.**

| # | Condition | Exception | Typical message |
|---|-----------|-----------|-----------------|
| 10.1 | Input `.docx` missing | `FileNotFoundError` | `Document not found: {path}` |
| 10.2 | Input path is not `.docx` | `ValueError` | `Expected a .docx file, got: {name}` |
| 10.3 | `docx2pdf` package not installed | `RuntimeError` | `docx2pdf is not installed. Run: pip install docx2pdf` |
| 10.4 | PDF file not created after convert | `RuntimeError` | `PDF was not created: {path}` |

**May stop pipeline (uncaught by `Main`):**

| # | Condition | Exception |
|---|-----------|-----------|
| 10.5 | Microsoft Word not installed or COM automation fails | Various from `docx2pdf` / Word |
| 10.6 | Word busy, file locked, invalid path | COM / `OSError` |
| 10.7 | Cannot write PDF to position folder | `PermissionError`, `OSError` |
| 10.8 | `docx2pdf` / Word COM from a **background thread** without per-thread init | `AttributeError` (e.g. `Open.SaveAs`) |

**Thread safety:** `convert_docx_to_pdf()` calls `pythoncom.CoInitialize()` before `docx2pdf.convert` and `pythoncom.CoUninitialize()` in `finally` when `pywin32` is available. This supports GUI workers that call `run_pipeline` from `threading.Thread`.

**Source:** `Modules/Pdf_Engine.py`

**Requires:** Windows + Microsoft Word for `docx2pdf`.

---

## 11. Page check — `config.Page_Checker.check_pdf_page_limit()`

**Does not stop** `run_pipeline()`. Issues are printed to stderr; result is still returned.

| # | Condition | Severity | Effect on `PipelineResult` |
|---|-----------|----------|----------------------------|
| 11.1 | Page check disabled in settings | — | `page_check_skipped=true`, `over_page_limit=false`, `page_count=null` |
| 11.2 | PDF file missing | Error issue | `page_count=null`, `over_page_limit=false` |
| 11.3 | `pypdf` not installed | Error issue (via `RuntimeError` caught) | Same |
| 11.4 | Path is not `.pdf` | Error issue | Same |
| 11.5 | PDF unreadable / other read error | Error issue (`OSError`, etc.) | Same |
| 11.6 | Page count exceeds limit | **Warning** issue | `over_page_limit=true`, `page_count` set |

**Warning message shape:** `WARNING pages: {n} pages in {filename} (limit {max} for resume)`  
**Error message shape:** `pages: {detail}` or `file: not found: {path}`

**Source:** `config/Page_Checker.py`

---

## 12. Pipeline progress callback — `Main.run_pipeline(on_progress=…)`

**Optional.** Does not stop the pipeline. Invoked synchronously from the pipeline thread (including GUI `threading.Thread` workers).

### Types

| Symbol | Module | Purpose |
|--------|--------|---------|
| `PipelineProgress` | `config.Pipeline_Progress` (re-exported from `Main`) | Frozen event: `phase`, `message`, `step`, `total_steps`, optional `detail` |
| `run_pipeline` | `Main` | Accepts `on_progress: Callable[[PipelineProgress], None] \| None = None` |

### `PipelineProgress` fields

| Field | Type | Use |
|-------|------|-----|
| `phase` | `str` | Machine id (see table below) |
| `message` | `str` | One plain-text line for the Result textbox |
| `step` | `int` | 1-based index for progress bar: `step / total_steps` |
| `total_steps` | `int` | Fixed for the run: `9 + cfg.trim.max_attempts` |
| `detail` | `str \| None` | Optional path or extra context (GUI may append on a second line) |

### Phase ids (`phase`)

| Phase | Typical `message` |
|-------|-------------------|
| `started` | Run started. |
| `validate_metadata` | Validating metadata… / Metadata validation passed. |
| `validate_bullets` | Validating bullets… / Bullet validation passed. |
| `application_folder` | Position folder: … |
| `fill_docx` | Creating DOCX… / Created DOCX: … |
| `convert_pdf` | Converting to PDF… / Created PDF: … |
| `page_check_initial` | Page check: N page(s) (limit M) — OK / OVER LIMIT / skipped |
| `trim` | Trim: removed bullet from … / Regenerating DOCX and PDF… |
| `page_check_final` | Final page check summary (same shape as initial) |
| `completed` | Run finished successfully. |
| `failed` | Generation failed: … (emitted once before re-raise) |

Trim steps use indices `8` … `7 + max_attempts`. If trim does not run, the bar advances from step 7 to `page_check_final` at `8 + max_attempts` (reserved slots are skipped; bar never moves backward).

### Thread safety

- Backend **only** calls `on_progress` synchronously; it must **not** touch Tk widgets.
- GUI: pass a callback that `put()`s events on `queue.Queue`; poll on the main thread with `after(50, …)`, append `event.message` (and optional `detail`) to the Result `CTkTextbox`, set `CTkProgressBar` to `event.step / event.total_steps`.
- On success, append final `PipelineResult` summary (paths, trim list) without duplicating lines already shown via progress.

### CLI

`run_cli` does not pass `on_progress`; behavior unchanged aside from PDF COM init (§10.8).

**Source:** `Main.py`, `config/Pipeline_Progress.py`

---

## 13. File logging — `config.logging_setup` / `config.Log_Path`

**Does not stop the pipeline.** Resume runs write append-only logs under `Logs/` (project root, sibling to `Applications/`).

| Item | Behavior |
|------|----------|
| Directory | `Logs/{company}/` — `company` uses the same sanitization as application folders (`sanitize_dir_name`) |
| Filename | `Resume_{Company}_{Position}_{YYYY-MM-DD}.log` — company/position segments use `Main.sanitize_filename_part` |
| One file per day | Multiple runs the same day append to the same file |
| Logger root | `resume` (handlers cleared per run in `finally`) |
| `document_type` | `"resume"` → `Resume_...`; `"cover_letter"` → `CoverLetter_...` in the same tree |

**Logged events (resume pipeline):** run start/end, JSON path or `dict input`, metadata pass/fail, bullet pass/fail, application folder, docx/pdf paths, trim removals, page check result, exceptions with traceback (`ERROR`).

**CLI:** On success, prints `Log: {path}` to stdout. stderr remains for user-facing page-check and trim messages.

**GUI:** No log viewer; generation uses the same `run_pipeline()` logging.

**Incomplete metadata:** If `company`/`position` are missing, log path uses `_unknown` segments under `Logs/_unknown/`.

**Source:** `config/Log_Path.py`, `config/logging_setup.py`, `Main.run_pipeline()`

---

## 14. Cover letter pipeline — `Main.run_cover_letter_pipeline()`

**Entry point:** `Main.run_cover_letter_pipeline()` (`Main.py`)

**Workflow:** Generate the resume first. Cover letter JSON is authored separately (e.g. via GPT) but must use the **same `company` and `position`** as the resume so outputs share `Applications/{company}/{position}/`.

### Pipeline order

1. Load config  
2. Load JSON  
3. File logging (`Logs/{company}/CoverLetter_{Company}_{Position}_{YYYY-MM-DD}.log`)  
4. Validate cover letter fields (`config/Cover_Letter_Validator.validate_cover_letter_data`)  
5. Resolve application folder (same as resume)  
6. Build output `.docx` path (`Ernesto_Carlton_Cover_Letter_{company}_{position}.docx`, `_2`, `_3` if needed)  
7. Fill cover letter (`Modules/Fill_Cover_Letter.fill_cover_letter`) — `{{ date }}` is **today** (not from JSON)  
8. Convert to PDF  
9. Page check (`document_type="cover_letter"`) — **non-fatal** if over limit  
10. No trim (`Modules/Trim_Cover_Letter` not implemented)

### Validation — `config/Cover_Letter_Validator`

**Stops pipeline.** `Main` raises `ValueError` with prefix `Cover letter validation failed:`.

Required fields (all non-empty after trim): `company`, `position`, `company_address`, `technical_area_from_job`, `your_project_that_matches`, `specific_challenge_you_solved`, `what_you_did`, `quantifiable_outcome`, `skill_from_job`, `previous_job_title`, `work_experience_lesson`, `why_this_company_unique`, `logistics_requirement`.

`department` is not used. `position` is required in JSON for folder and filename alignment with the resume, not necessarily as a body placeholder. `date` is pipeline-injected (not from JSON).

### Over page limit

Same as resume: run **succeeds** with `CoverLetterPipelineResult.over_page_limit=True`; warnings on stderr and in log. No trim.

### Progress

Optional `on_progress` callback; 7 steps (no trim). Phase ids: `cover_letter_started`, `cover_letter_validate`, `cover_letter_application_folder`, `cover_letter_fill_docx`, `cover_letter_convert_pdf`, `cover_letter_page_check`, `cover_letter_completed`, `cover_letter_failed`.

### CLI

```bash
python Main.py --cover-letter sample_cover_letter_data.json
```

Without `--cover-letter`, a JSON path runs the **resume** pipeline only.

**Source:** `Main.py`, `Modules/Fill_Cover_Letter.py`, `config/Cover_Letter_Validator.py`

---

## 15. Temporary job Markdown — `Modules.Job_Md.save_temporary_job_md()`

**Does not run resume or cover letter pipelines.**

| # | Condition | Exception | Typical message |
|---|-----------|-----------|-----------------|
| 15.1 | Description empty after trim | `ValueError` | `Job description must be non-empty after trim` |
| 15.2 | URL empty after trim | `ValueError` | `Job posting URL must be non-empty after trim` |
| 15.3 | Invalid `Job_MD/.sequence` | `ValueError` | Invalid `.sequence` contents |

**Behavior:** Each save deletes prior `job_*.md` in `Job_MD/`, increments `.sequence`, writes `job_{NNN}.md`. Folder is gitignored.

**Source:** `Modules/Job_Md.py`

---

## 16. Application file delete — `Modules.Application_Delete`

**Does not run pipelines.** Used by GUI (later) to remove generated outputs under `Applications/`.

| # | Condition | Exception / result |
|---|-----------|-------------------|
| 16.1 | Path outside `Applications/` | `ValueError` — `Path is not under Applications/` |
| 16.2 | Not `.docx` or `.pdf` | `ValueError` |
| 16.3 | Path is a directory (single-file delete) | `ValueError` — `Path is not a file` |
| 16.4 | Primary file missing | `FileNotFoundError` |
| 16.5 | Paired sibling missing (`--pair`) | `DeleteResult.skipped` |
| 16.6 | Delete succeeds | `DeleteResult.deleted` |
| 16.7 | OS error on unlink | `DeleteResult.errors` (non-fatal entry) |

**CLI:** `python Modules/Application_Delete.py path\to\file.docx [--pair]`

**Position folder:** `delete_position_folder()` removes `Applications/{company}/{position}/` (validated two levels below root).

**Source:** `Modules/Application_Delete.py`

---

## 17. CLI only — `Main.main()`

| # | Condition | Behavior |
|---|-----------|----------|
| 17.1 | Invalid CLI arguments | `argparse` exits with usage help |
| 17.2 | Resume pipeline failure | Catches `FileNotFoundError`, `ValueError`, `JSONDecodeError`, `RuntimeError` → prints `Error: {exc}` → exit code `1` |
| 17.3 | `--cover-letter` without JSON path | Prints error → exit code `1` |
| 17.4 | Cover letter pipeline failure | Same exceptions as resume CLI → exit code `1` |

**Not caught by CLI today:** `OSError`, `PermissionError`, Word/COM errors, most `python-docx` errors → uncaught traceback.

---

## Suggested error codes (for later — not implemented)

| Code prefix | Maps to sections |
|-------------|------------------|
| `CONFIG_*` | §1 |
| `JSON_*` | §2 |
| `VALIDATION_METADATA_*` | §3 |
| `VALIDATION_BULLET_*` | §4 |
| `APPLICATION_*` | §5 |
| `OUTPUT_*` | §6 |
| `TEMPLATE_*` | §7 |
| `RESUME_DATA_*` | §8 |
| `FILL_*` | §9 |
| `PDF_*` | §10 |
| `PAGE_CHECK_*` | §11 (non-fatal) |
| `PAGE_OVER_LIMIT` | Flag only; trim may reduce pages when enabled |
| `PROGRESS_*` | §12 (informational) |
| `LOG_*` | §13 (informational) |
| `SYSTEM_*` | §5.3, §9.5–9.7, §10.5–10.8 |

---

## Known gaps (fix after GUI)

1. **Duplicate validation:** Bullet shape (4.x) vs parse (8.x) — validator does not catch all issues `parse_resume_data` catches.  
2. **No stable error codes** — only exception types and string messages.  
3. **Page check is non-fatal** — GUI should treat `over_page_limit` separately from hard errors.  
4. **System errors uncaught** — permissions, Word, disk, corrupt docx often surface as raw tracebacks.  
5. **`validate_json_file` file errors** — not used by `Main` when loading by path (Main loads JSON itself first).  
6. **Application folder checks** — metadata validation (§3) runs before `Application_Path`; folder errors (§5) are largely redundant when metadata passes.

---

## Related files

| File | Purpose |
|------|---------|
| `Main.py` | Orchestration, `PipelineResult`, CLI |
| `config/Loader.py` | Settings load/parse |
| `config/Pipeline_Progress.py` | `PipelineProgress`, step totals |
| `config/Metadata_Validator.py` | Required metadata fields |
| `config/Validator.py` | Metadata + bullet validation |
| `config/Log_Path.py` | Log file path under `Logs/` |
| `config/logging_setup.py` | Per-run file handler |
| `Modules/Trim_Resume.py` | Page-limit bullet trim |
| `config/Page_Checker.py` | PDF page count |
| `config/Issues.py` | `ValidationIssue`, `ValidationResult` |
| `Modules/Application_Path.py` | `Applications/{company}/{position}/` |
| `Modules/Fill_Cover_Letter.py` | Cover letter template fill |
| `config/Cover_Letter_Validator.py` | Cover letter required fields |
| `Main.run_cover_letter_pipeline` | Cover letter orchestration |
| `Modules/Fill_Resume.py` | Template fill |
| `Modules/Pdf_Engine.py` | DOCX → PDF |
