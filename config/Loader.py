"""Load and interpret config/settings.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_SETTINGS_PATH = CONFIG_DIR / "settings.json"
KNOWN_TEMPLATE_TYPES = ("resume", "cover_letter")
KNOWN_TRIM_REMOVE = ("bullets",)
DEFAULT_TRIM_ORDER: tuple[dict[str, str], ...] = (
    {"section": "greenway", "remove": "bullets"},
    {"section": "windturbine", "remove": "bullets"},
    {"section": "peizo", "remove": "bullets"},
    {"section": "mostardi", "remove": "bullets"},
    {"section": "goose", "remove": "bullets"},
)


@dataclass
class TemplateConfig:
    """One document type (resume, cover letter, etc.)."""

    name: str
    enabled: bool
    path: Path | None


@dataclass
class BulletLimits:
    """Character and count limits for a bullet group prefix (e.g. goose)."""

    max_characters: int
    max_count: int


@dataclass
class PageLimitConfig:
    """Page limit for a document type (resume, cover letter, etc.)."""

    name: str
    max_pages: int
    check_enabled: bool


@dataclass
class TrimStep:
    """One trim action applied when a document exceeds the page limit."""

    section: str
    remove: str


@dataclass
class TrimConfig:
    """Auto-trim rules for fitting content within the page limit."""

    enabled: bool
    max_attempts: int
    order: list[TrimStep] = field(default_factory=list)


@dataclass
class Config:
    """Full project configuration from settings.json."""

    templates: dict[str, TemplateConfig] = field(default_factory=dict)
    bullet_defaults: BulletLimits = field(
        default_factory=lambda: BulletLimits(max_characters=120, max_count=6)
    )
    bullet_groups: dict[str, BulletLimits] = field(default_factory=dict)
    page_defaults: int = 1
    page_limits: dict[str, PageLimitConfig] = field(default_factory=dict)
    trim: TrimConfig = field(
        default_factory=lambda: TrimConfig(
            enabled=True,
            max_attempts=10,
            order=[TrimStep(**step) for step in DEFAULT_TRIM_ORDER],
        )
    )
    settings_path: Path = field(default_factory=lambda: DEFAULT_SETTINGS_PATH)

    def enabled_templates(self) -> list[TemplateConfig]:
        return [t for t in self.templates.values() if t.enabled]

    def template(self, name: str) -> TemplateConfig | None:
        return self.templates.get(name)

    def limits_for_group(self, prefix: str) -> BulletLimits:
        if prefix in self.bullet_groups:
            return self.bullet_groups[prefix]
        return self.bullet_defaults

    def max_pages_for(self, document_type: str) -> int:
        if document_type in self.page_limits:
            return self.page_limits[document_type].max_pages
        return self.page_defaults

    def page_check_enabled(self, document_type: str) -> bool:
        if document_type in self.page_limits:
            return self.page_limits[document_type].check_enabled
        return True


def project_root() -> Path:
    return CONFIG_DIR.parent


def resolve_path(path: Path, base: Path | None = None) -> Path:
    root = base or project_root()
    return path if path.is_absolute() else root / path


def _require_int(value: Any, field_name: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f'"{field_name}" must be an integer')
    if value < minimum:
        raise ValueError(f'"{field_name}" must be at least {minimum}, got {value}')
    return value


def _parse_template_entry(name: str, raw: Any) -> TemplateConfig:
    if not isinstance(raw, dict):
        raise ValueError(f'templates.{name} must be an object')

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError(f'templates.{name}.enabled must be true or false')

    path_raw = raw.get("path")
    path: Path | None = None
    if path_raw is not None:
        if not isinstance(path_raw, str) or not path_raw.strip():
            raise ValueError(f'templates.{name}.path must be a non-empty string or null')
        path = Path(path_raw.strip())

    if enabled and path is None:
        raise ValueError(f'templates.{name} is enabled but path is not set')

    return TemplateConfig(name=name, enabled=enabled, path=path)


def _parse_bullet_limits(raw: Any, context: str) -> BulletLimits:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be an object")

    max_chars = raw.get("max_characters", raw.get("default_max_characters"))
    max_count = raw.get("max_count", raw.get("default_max_count", raw.get("max_bullets")))

    if max_chars is None:
        raise ValueError(f'{context} must include "max_characters"')
    if max_count is None:
        raise ValueError(f'{context} must include "max_count" (or "max_bullets")')

    return BulletLimits(
        max_characters=_require_int(max_chars, f"{context}.max_characters"),
        max_count=_require_int(max_count, f"{context}.max_count"),
    )


def _parse_trim_step(raw: Any, context: str) -> TrimStep:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be an object")

    section = raw.get("section")
    if not isinstance(section, str) or not section.strip():
        raise ValueError(f'{context}.section must be a non-empty string')

    remove = raw.get("remove")
    if not isinstance(remove, str) or not remove.strip():
        raise ValueError(f'{context}.remove must be a non-empty string')
    remove = remove.strip()
    if remove not in KNOWN_TRIM_REMOVE:
        raise ValueError(
            f'{context}.remove must be one of {KNOWN_TRIM_REMOVE}, got "{remove}"'
        )

    return TrimStep(section=section.strip(), remove=remove)


def _parse_trim(raw: Any) -> TrimConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError('"trim" must be an object')

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError('trim.enabled must be true or false')

    max_attempts = _require_int(raw.get("max_attempts", 10), "trim.max_attempts")

    order_raw = raw.get("order", list(DEFAULT_TRIM_ORDER))
    if not isinstance(order_raw, list):
        raise ValueError('trim.order must be an array')

    order: list[TrimStep] = []
    for index, step_raw in enumerate(order_raw, start=1):
        order.append(_parse_trim_step(step_raw, f"trim.order[{index}]"))

    return TrimConfig(enabled=enabled, max_attempts=max_attempts, order=order)


def _sort_known_first(names: list[str] | set[str], known: tuple[str, ...]) -> list[str]:
    known_set = set(known)
    return sorted(names, key=lambda n: (n not in known_set, n))


def _parse_settings(raw: dict) -> Config:
    """Parse a settings dict using the same rules as settings.json."""
    templates_raw = raw.get("templates", {})
    if not isinstance(templates_raw, dict):
        raise ValueError('"templates" must be an object')

    templates: dict[str, TemplateConfig] = {}
    for name in KNOWN_TEMPLATE_TYPES:
        entry = templates_raw.get(name, {"enabled": False, "path": None})
        templates[name] = _parse_template_entry(name, entry)

    for name in templates_raw:
        if name not in templates:
            templates[name] = _parse_template_entry(name, templates_raw[name])

    bullets_raw = raw.get("bullets", {})
    if not isinstance(bullets_raw, dict):
        raise ValueError('"bullets" must be an object')

    defaults = BulletLimits(
        max_characters=_require_int(
            bullets_raw.get("default_max_characters", 120),
            "bullets.default_max_characters",
        ),
        max_count=_require_int(
            bullets_raw.get("default_max_count", 6),
            "bullets.default_max_count",
        ),
    )

    groups_raw = bullets_raw.get("groups", {})
    if not isinstance(groups_raw, dict):
        raise ValueError('"bullets.groups" must be an object')

    bullet_groups: dict[str, BulletLimits] = {}
    for prefix, group_raw in groups_raw.items():
        if not isinstance(prefix, str) or not prefix.strip():
            raise ValueError("bullets.groups keys must be non-empty strings")
        merged = {
            "max_characters": group_raw.get("max_characters", defaults.max_characters)
            if isinstance(group_raw, dict)
            else defaults.max_characters,
            "max_count": group_raw.get("max_count", group_raw.get("max_bullets", defaults.max_count))
            if isinstance(group_raw, dict)
            else defaults.max_count,
        }
        bullet_groups[prefix.strip()] = _parse_bullet_limits(merged, f"bullets.groups.{prefix}")

    pages_raw = raw.get("pages", {})
    if not isinstance(pages_raw, dict):
        raise ValueError('"pages" must be an object')

    page_defaults = _require_int(
        pages_raw.get("default_max_pages", 1),
        "pages.default_max_pages",
    )

    page_limits: dict[str, PageLimitConfig] = {}
    for name in KNOWN_TEMPLATE_TYPES:
        entry = pages_raw.get(name, {})
        if not isinstance(entry, dict):
            entry = {}
        page_limits[name] = PageLimitConfig(
            name=name,
            max_pages=_require_int(entry.get("max_pages", page_defaults), f"pages.{name}.max_pages"),
            check_enabled=entry.get("check_enabled", name == "resume"),
        )
        if not isinstance(page_limits[name].check_enabled, bool):
            raise ValueError(f'pages.{name}.check_enabled must be true or false')

    for name, entry in pages_raw.items():
        if name == "default_max_pages" or name in page_limits:
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"pages.{name} must be an object")
        check_enabled = entry.get("check_enabled", True)
        if not isinstance(check_enabled, bool):
            raise ValueError(f"pages.{name}.check_enabled must be true or false")
        page_limits[name] = PageLimitConfig(
            name=name,
            max_pages=_require_int(entry.get("max_pages", page_defaults), f"pages.{name}.max_pages"),
            check_enabled=check_enabled,
        )

    trim = _parse_trim(raw.get("trim"))

    return Config(
        templates=templates,
        bullet_defaults=defaults,
        bullet_groups=bullet_groups,
        page_defaults=page_defaults,
        page_limits=page_limits,
        trim=trim,
    )


def config_from_dict(raw: dict) -> Config:
    """Parse and validate a settings dict (same rules as load_config)."""
    if not isinstance(raw, dict):
        raise ValueError("Settings root must be a JSON object")
    return _parse_settings(raw)


def config_to_dict(cfg: Config) -> dict:
    """Convert Config to a dict matching settings.json layout."""
    templates: dict[str, dict] = {}
    for name in _sort_known_first(cfg.templates.keys(), KNOWN_TEMPLATE_TYPES):
        template = cfg.templates[name]
        templates[name] = {
            "enabled": template.enabled,
            "path": template.path.as_posix() if template.path else None,
        }

    groups: dict[str, dict] = {}
    for prefix in sorted(cfg.bullet_groups):
        group = cfg.bullet_groups[prefix]
        groups[prefix] = {
            "max_characters": group.max_characters,
            "max_count": group.max_count,
        }

    pages: dict[str, Any] = {"default_max_pages": cfg.page_defaults}
    for name in _sort_known_first(cfg.page_limits.keys(), KNOWN_TEMPLATE_TYPES):
        page = cfg.page_limits[name]
        pages[name] = {
            "max_pages": page.max_pages,
            "check_enabled": page.check_enabled,
        }

    trim_order = [
        {"section": step.section, "remove": step.remove} for step in cfg.trim.order
    ]

    return {
        "templates": templates,
        "bullets": {
            "default_max_characters": cfg.bullet_defaults.max_characters,
            "default_max_count": cfg.bullet_defaults.max_count,
            "groups": groups,
        },
        "pages": pages,
        "trim": {
            "enabled": cfg.trim.enabled,
            "max_attempts": cfg.trim.max_attempts,
            "order": trim_order,
        },
    }


def load_config(settings_path: Path | None = None) -> Config:
    """Load settings.json and return a Config object."""
    path = (settings_path or DEFAULT_SETTINGS_PATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Settings file not found: {path}")

    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    cfg = config_from_dict(raw)
    cfg.settings_path = path
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    """Write Config to settings.json (default: cfg.settings_path or DEFAULT_SETTINGS_PATH)."""
    out = (path or cfg.settings_path or DEFAULT_SETTINGS_PATH).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(config_to_dict(cfg), f, indent=2)
        f.write("\n")
    cfg.settings_path = out


def resolve_template_path(template: TemplateConfig, base: Path | None = None) -> Path:
    """Resolve a template's path relative to the project root."""
    if template.path is None:
        raise ValueError(f'Template "{template.name}" has no path configured')
    return resolve_path(template.path, base)
