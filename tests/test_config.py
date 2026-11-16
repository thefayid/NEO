"""
tests/test_config.py — Tests for NEO configuration management.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
import yaml

from neo.config import NeoSettings, get_settings, load_settings


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Cleans up NEO_ environment variables before and after each test."""
    to_clear = [k for k in os.environ if k.startswith("NEO_")]
    for k in to_clear:
        del os.environ[k]
    yield
    to_clear = [k for k in os.environ if k.startswith("NEO_")]
    for k in to_clear:
        del os.environ[k]


def test_default_settings():
    settings = NeoSettings()
    assert "gemini" in settings.model_name
    assert "notepad.exe" in settings.allowed_apps
    assert len(settings.allowed_folders) > 0
    assert settings.timeouts["action"] == 30.0
    assert settings.retry_limits["action"] == 3
    assert settings.log_path.endswith(".jsonl")


def test_load_from_yaml(tmp_path: Path):
    yaml_file = tmp_path / "custom_config.yaml"
    data = {
        "model_name": "models/custom-planner-pro",
        "allowed_apps": ["calc.exe", "custom_tool.exe"],
        "allowed_folders": [str(tmp_path / "sandbox")],
        "timeouts": {
            "action": 45.5,
            "step": 90.0,
        },
        "retry_limits": {
            "action": 5,
            "step": 3,
        },
        "log_path": str(tmp_path / "logs" / "custom_steps.jsonl"),
    }
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    settings = load_settings(yaml_file=yaml_file)

    assert settings.model_name == "models/custom-planner-pro"
    assert settings.allowed_apps == ["calc.exe", "custom_tool.exe"]
    assert str(tmp_path / "sandbox") in settings.allowed_folders[0]
    assert settings.timeouts["action"] == 45.5
    assert settings.retry_limits["action"] == 5
    assert settings.log_path == str(tmp_path / "logs" / "custom_steps.jsonl")


def test_env_override_over_yaml(tmp_path: Path):
    yaml_file = tmp_path / "base.yaml"
    data = {
        "model_name": "yaml-model",
        "timeouts": {"action": 20.0},
    }
    yaml_file.write_text(yaml.dump(data), encoding="utf-8")

    os.environ["NEO_MODEL_NAME"] = "env-model-override"
    os.environ["NEO_LOG_PATH"] = str(tmp_path / "env_log.jsonl")

    # Env takes precedence over YAML
    settings = load_settings(yaml_file=yaml_file)
    assert settings.model_name == "env-model-override"
    assert settings.log_path == str(tmp_path / "env_log.jsonl")
    assert settings.timeouts["action"] == 20.0


def test_comma_separated_env_lists():
    os.environ["NEO_ALLOWED_APPS"] = "app1.exe, App2.exe , app3.exe "
    settings = NeoSettings()
    assert settings.allowed_apps == ["app1.exe", "app2.exe", "app3.exe"]


def test_invalid_timeouts_raise_error():
    with pytest.raises(ValueError, match="must be positive"):
        NeoSettings(timeouts={"action": -10.0})

    with pytest.raises(ValueError, match="must be positive"):
        NeoSettings(timeouts={"action": 0.0})


def test_invalid_retries_raise_error():
    with pytest.raises(ValueError, match="cannot be negative"):
        NeoSettings(retry_limits={"action": -1})


def test_direct_overrides_have_highest_precedence(tmp_path: Path):
    yaml_file = tmp_path / "base.yaml"
    yaml_file.write_text(yaml.dump({"model_name": "yaml-model"}), encoding="utf-8")
    os.environ["NEO_MODEL_NAME"] = "env-model"

    settings = load_settings(yaml_file=yaml_file, model_name="explicit-override")
    assert settings.model_name == "explicit-override"


def test_get_settings_caching():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
