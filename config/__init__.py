"""Project configuration: templates, bullet limits, and JSON validation."""

from config.Loader import (
    DEFAULT_SETTINGS_PATH,
    BulletLimits,
    Config,
    PageLimitConfig,
    TemplateConfig,
    TrimConfig,
    TrimStep,
    config_from_dict,
    config_to_dict,
    load_config,
    project_root,
    resolve_path,
    resolve_template_path,
    save_config,
)

__all__ = [
    "DEFAULT_SETTINGS_PATH",
    "BulletLimits",
    "Config",
    "PageLimitConfig",
    "TemplateConfig",
    "TrimConfig",
    "TrimStep",
    "config_from_dict",
    "config_to_dict",
    "load_config",
    "project_root",
    "resolve_path",
    "resolve_template_path",
    "save_config",
]
