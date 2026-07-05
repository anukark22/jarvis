"""Local config storage for Jarvis.

Stores settings (API key, wake word toggle) in a small JSON file under the
user's home directory, so you're not retyping your API key every launch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".jarvis"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "provider": "anthropic",      # "anthropic" or "gemini"
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-5",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "wake_word": "jarvis",
    "muted": False,
}


def load_config() -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(DEFAULTS)
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_config(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_provider() -> str:
    return load_config().get("provider", "anthropic")


def set_provider(provider: str) -> None:
    cfg = load_config()
    cfg["provider"] = provider
    save_config(cfg)


def get_api_key(provider: str | None = None) -> str:
    """API key resolution order: env var, then saved config, for whichever
    provider is active (or explicitly passed)."""
    provider = provider or get_provider()
    env_name = "ANTHROPIC_API_KEY" if provider == "anthropic" else "GEMINI_API_KEY"
    env_key = os.environ.get(env_name, "").strip()
    if env_key:
        return env_key
    cfg = load_config()
    return cfg.get(f"{provider}_api_key", "").strip()


def set_api_key(key: str, provider: str | None = None) -> None:
    provider = provider or get_provider()
    cfg = load_config()
    cfg[f"{provider}_api_key"] = key.strip()
    save_config(cfg)


def get_model(provider: str | None = None) -> str:
    provider = provider or get_provider()
    cfg = load_config()
    return cfg.get(f"{provider}_model", "")
