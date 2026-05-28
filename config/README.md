# Configuration

This folder controls which document templates are used, enforces bullet limits on resume JSON data, and warns when a generated document exceeds the page limit. It is standalone for now; the main fill script will read these settings when wired up later.

## Files

| File | Purpose |
|------|---------|
| `settings.json` | Edit this to choose templates and set bullet limits |
| `Loader.py` | Loads `settings.json` into Python objects |
| `Validator.py` | Checks a JSON file against bullet limits |
| `Page_Checker.py` | Checks a generated `.docx` against page limits |
| `templates/` | Optional place to store `.docx` templates |

## Template selection

In `settings.json`, under `templates`:

- **resume** — set `enabled` to `true` and `path` to your `.docx` file (relative to the project root, or an absolute path).
- **cover_letter** — set `enabled` to `true` and `path` to `config/templates/Cover_Letter_Template.docx`.

**Cover letter CLI (Main):**

```bash
python Main.py --cover-letter sample_cover_letter_data.json
```

Required JSON fields: `company`, `position`, `company_address`, `technical_area_from_job`, `your_project_that_matches`, `specific_challenge_you_solved`, `what_you_did`, `quantifiable_outcome`, `skill_from_job`, `previous_job_title`, `work_experience_lesson`, `why_this_company_unique`, `logistics_requirement`. Use the same `company` and `position` as the resume JSON so both documents share `Applications/{company}/{position}/`. `position` is for paths and filenames only—the template body may not include `{{ position }}` or `{{ department }}`. `{{ date }}` is set by the pipeline (not from JSON).

Standalone fill only: `python Modules/Fill_Cover_Letter.py sample_cover_letter_data.json -o out.docx`.

To use a new resume layout:

1. Copy your `.docx` into `config/templates/` (recommended) or anywhere in the project.
2. Update `templates.resume.path`, for example: `"config/templates/My_Resume.docx"`.
3. Keep `enabled` as `true`.

Paths are resolved from the project root (the folder that contains `Fill_Resume.py`).

## Bullet limits

Under `bullets` in `settings.json`:

| Setting | Meaning |
|---------|---------|
| `default_max_characters` | Max characters per bullet (all groups unless overridden) |
| `default_max_count` | Max bullets per experience section |
| `groups` | Per-section overrides keyed by prefix (without `_bullets`) |

Example — stricter limits only for `goose`:

```json
"groups": {
  "goose": {
    "max_characters": 100,
    "max_count": 4
  }
}
```

JSON keys validated: `goose_bullets`, `peizo_bullets`, etc., and flat keys like `goose_bullet_1`.

## Page limits

Under `pages` in `settings.json`:

| Setting | Meaning |
|---------|---------|
| `default_max_pages` | Default max pages for any document type without its own entry |
| `resume.max_pages` | Max pages for resume output (currently **1**) |
| `resume.check_enabled` | Whether to run the page check after a resume is generated |
| `cover_letter.*` | Same shape; disabled until you use cover letters |

Page count is measured **after** a `.docx` is built: the file is converted to PDF via Word (`docx2pdf`), then pages are counted with `pypdf`. Microsoft Word must be installed on Windows.

From the project root, after `Fill_Resume.py` creates a file:

```bash
python -m config.Page_Checker Test_Docs/Ernesto_Carlton_Resume_Company_Position.docx --type resume
```

Resume JSON must include `company` and `position`. Output is named `Ernesto_Carlton_Resume_{Company}_{Position}.docx` in `Test_Docs/`.

If over the limit:

```
WARNING pages: 2 pages in Ernesto_Carlton_Resume_....docx (limit 1 for resume)
```

The command exits with code `1` when over limit so you can hook it into the main process later.

## Validate JSON from the command line

From the project root:

```bash
python -m config.Validator sample_data.json
```

On failure, each issue is listed with the field path and what exceeded the limit.

## Python usage (for later integration)

```python
from pathlib import Path

from config import load_config, resolve_template_path
from config.Page_Checker import check_page_limit
from config.Validator import validate_json_file

cfg = load_config()
result = validate_json_file(Path("sample_data.json"), cfg)
if not result.valid:
    for msg in result.messages():
        print(msg)

# After Fill_Resume creates output_path:
page_result = check_page_limit(output_path, document_type="resume", config=cfg)
for msg in page_result.warning_messages():
    print(msg)

resume = cfg.template("resume")
if resume and resume.enabled:
    docx_path = resolve_template_path(resume)
```
