"""
neo/config.py — Central Configuration Management for NEO.

Loads configuration settings using Pydantic Settings from:
1. Explicit initialization keyword arguments
2. Environment variables (prefixed with NEO_, e.g. NEO_MODEL_NAME)
3. YAML configuration file (config.yaml by default, or path specified via NEO_CONFIG_PATH / load_settings)
"""
from __future__ import annotations

import contextvars
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import yaml
from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_DEFAULT_YAML_NAME = "config.yaml"
_BASE_DIR = Path(__file__).resolve().parent.parent
_yaml_file_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("yaml_file", default=None)


class CustomEnvSource(EnvSettingsSource):
    """Custom EnvSettingsSource that seamlessly handles comma-separated list values."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        try:
            return super().decode_complex_value(field_name, field, value)
        except Exception:
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            return value


def _default_allowed_apps() -> List[str]:
    return [
        "notepad.exe",
        "calc.exe",
        "explorer.exe",
        "msedge.exe",
        "chrome.exe",
        "code.exe",
        "cmd.exe",
        "powershell.exe",
        "spotify.exe",
    ]


def _default_allowed_folders() -> List[str]:
    home = Path.home()
    return [
        str(home / "Desktop"),
        str(home / "Documents"),
        str(home / "Downloads"),
        str(_BASE_DIR),
    ]


def _default_allowed_domains() -> List[str]:
    return [
        "google.com",
        "github.com",
        "microsoft.com",
        "wikipedia.org",
        "bing.com",
        "stackoverflow.com",
        "python.org",
        "127.0.0.1",
        "localhost",
    ]


def _default_timeouts() -> Dict[str, float]:
    return {
        "action": 30.0,
        "step": 60.0,
        "overall": 300.0,
        "browser": 45.0,
        "uia": 15.0,
    }


def _default_retry_limits() -> Dict[str, int]:
    return {
        "action": 3,
        "step": 2,
        "network": 4,
    }


class NeoSettings(BaseSettings):
    """
    Strongly typed settings for NEO personal assistant.
    """
    model_name: str = Field(
        default="models/gemini-2.5-flash",
        description="LLM model identifier used for decision planning and reasoning.",
    )
    allowed_apps: List[str] = Field(
        default_factory=_default_allowed_apps,
        description="Strict allow-list of executable names or paths NEO is permitted to launch or control.",
    )
    allowed_folders: List[str] = Field(
        default_factory=_default_allowed_folders,
        description="Strict allow-list of directory paths NEO is permitted to read or modify.",
    )
    allowed_domains: List[str] = Field(
        default_factory=_default_allowed_domains,
        description="Strict allow-list of domains NEO is permitted to navigate to in browser.",
    )
    timeouts: Dict[str, float] = Field(
        default_factory=_default_timeouts,
        description="Timeout thresholds in seconds for different action and execution tiers.",
    )
    retry_limits: Dict[str, int] = Field(
        default_factory=_default_retry_limits,
        description="Maximum retry attempts allowed per action, step, or network operation.",
    )
    log_path: str = Field(
        default="logs/neo_steps.jsonl",
        description="File path where structured JSON-lines step execution logs are persisted.",
    )
    yaml_config_path: Optional[str] = Field(
        default=None,
        description="Explicit path to YAML configuration file if provided.",
    )

    model_config = SettingsConfigDict(
        env_prefix="NEO_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @field_validator("allowed_apps", mode="before")
    @classmethod
    def _validate_apps(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            # Support comma-separated strings from env vars: NEO_ALLOWED_APPS="notepad.exe,calc.exe"
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        if isinstance(v, (list, tuple)):
            return [str(item).strip().lower() for item in v if str(item).strip()]
        return v

    @field_validator("allowed_folders", mode="before")
    @classmethod
    def _validate_folders(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [str(Path(item.strip()).resolve()) for item in v.split(",") if item.strip()]
        if isinstance(v, (list, tuple)):
            return [str(Path(item).resolve()) for item in v]
        return v

    @field_validator("timeouts", mode="before")
    @classmethod
    def _validate_timeouts(cls, v: Any) -> Dict[str, float]:
        if isinstance(v, dict):
            out: Dict[str, float] = {}
            for k, val in v.items():
                f_val = float(val)
                if f_val <= 0:
                    raise ValueError(f"Timeout for '{k}' must be positive, got {f_val}")
                out[str(k).lower()] = f_val
            return out
        return v

    @field_validator("retry_limits", mode="before")
    @classmethod
    def _validate_retries(cls, v: Any) -> Dict[str, int]:
        if isinstance(v, dict):
            out: Dict[str, int] = {}
            for k, val in v.items():
                i_val = int(val)
                if i_val < 0:
                    raise ValueError(f"Retry limit for '{k}' cannot be negative, got {i_val}")
                out[str(k).lower()] = i_val
            return out
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init overrides > env vars > yaml file > dotenv > file secrets
        custom_yaml = _yaml_file_var.get() or os.environ.get("NEO_CONFIG_PATH") or str(_BASE_DIR / _DEFAULT_YAML_NAME)
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=custom_yaml)
        return (
            init_settings,
            CustomEnvSource(settings_cls),
            yaml_source,
            dotenv_settings,
            file_secret_settings,
        )


_cached_settings: Optional[NeoSettings] = None


def load_settings(yaml_file: Optional[Union[str, Path]] = None, **overrides: Any) -> NeoSettings:
    """
    Loads and returns a NeoSettings instance.
    If yaml_file is provided, it reads configuration directly from that YAML file.
    Precedence: overrides > env vars > YAML file > defaults.
    """
    global _cached_settings
    yaml_str = str(Path(yaml_file).resolve()) if yaml_file else None
    token = _yaml_file_var.set(yaml_str)
    try:
        init_kwargs = dict(overrides)
        if yaml_str:
            init_kwargs["yaml_config_path"] = yaml_str
        settings = NeoSettings(**init_kwargs)
        _cached_settings = settings
        return settings
    finally:
        _yaml_file_var.reset(token)


def get_settings() -> NeoSettings:
    """Returns the active cached settings instance, initializing from defaults if needed."""
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = load_settings()
    return _cached_settings
