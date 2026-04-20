"""Configuration system for FreeCAD AI.

Stores settings as JSON at ~/.config/FreeCAD/FreeCADAI/config.json
"""

import json
import os
from dataclasses import dataclass, field, asdict


CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "FreeCAD", "FreeCADAI")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CONVERSATIONS_DIR = os.path.join(CONFIG_DIR, "conversations")
SKILLS_DIR = os.path.join(CONFIG_DIR, "skills")
USER_TOOLS_DIR = os.path.join(CONFIG_DIR, "tools")
HOOKS_DIR = os.path.join(CONFIG_DIR, "hooks")

# Provider presets — derived from the canonical PROVIDERS dict in llm/providers.py.
# Each preset contains only base_url and default_model (the fields the Settings
# dialog needs for auto-filling when the user switches providers).
from .llm.providers import PROVIDERS as _PROVIDERS

PROVIDER_PRESETS = {
    name: {
        "base_url": p["base_url"],
        "default_model": p["default_model"],
        "default_params": p.get("default_params", {}),
    }
    for name, p in _PROVIDERS.items()
}


@dataclass
class ProviderConfig:
    name: str = "anthropic"
    api_key: str = ""
    base_url: str = "https://api.anthropic.com"
    model: str = "claude-sonnet-4-20250514"

    def apply_preset(self, provider_name: str):
        """Apply a provider preset, updating base_url and model to defaults."""
        preset = PROVIDER_PRESETS.get(provider_name, {})
        self.name = provider_name
        self.base_url = preset.get("base_url", self.base_url)
        self.model = preset.get("default_model", self.model)


@dataclass
class AppConfig:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    mode: str = "plan"  # "plan" or "act"
    max_tokens: int = 4096
    context_window: int = 20000  # tokens — compaction triggers above this
    temperature: float = 0.3
    model_params: dict = field(default_factory=dict)
    # Per-model parameter overrides, keyed by model name:
    # {"gemma4:27b": {"temperature": 1.0, "top_p": 0.95, "top_k": 64}, ...}
    auto_execute: bool = False
    max_retries: int = 3
    enable_tools: bool = True
    thinking: str = "off"  # "off", "on", "extended"
    strip_thinking_history: bool | None = None  # None=auto-detect, True/False=override
    viewport_capture: str = "off"  # "off", "every_message", "after_changes"
    viewport_resolution: str = "medium"  # "low", "medium", "high"
    mcp_servers: list = field(default_factory=list)
    # Each entry: {"name": str, "command": str, "args": list, "env": dict, "enabled": bool}
    user_tools_disabled: list = field(default_factory=list)
    scan_freecad_macros: bool = False
    hooks_disabled: list = field(default_factory=list)
    system_prompt_override: str = ""  # empty = use default; non-empty = use as-is
    vision_detected: bool | None = None   # None=not tested, True/False=probe result
    vision_override: bool | None = None   # user manual override, takes precedence

    # Tool reranking — when active, only the top-N most relevant tools
    # (plus pinned tools) are sent to the LLM on each user turn. Saves
    # prompt tokens when many tools are registered.
    # "off" = disabled, "keyword" = IDF-weighted token match (free, fast),
    # "llm" = semantic ranking via a small/fast LLM (better filter quality).
    rerank_method: str = "off"
    rerank_top_n: int = 15
    rerank_pinned_tools: list = field(default_factory=list)
    # LLM reranker provider override. Empty = inherit from main provider.
    # Lets users run reranking through a cheap/local model (e.g. Ollama)
    # while the main chat uses an expensive cloud model.
    rerank_llm_provider_name: str = ""
    rerank_llm_base_url: str = ""
    rerank_llm_api_key: str = ""
    rerank_llm_model: str = ""

    @property
    def supports_vision(self) -> bool:
        """Whether the current LLM supports vision (images in content blocks)."""
        if self.vision_override is not None:
            return self.vision_override
        if self.vision_detected is not None:
            return self.vision_detected
        return False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        provider_data = data.pop("provider", {})
        provider = ProviderConfig(**provider_data)
        # Filter out unknown keys to avoid TypeError
        known = {f.name for f in cls.__dataclass_fields__.values()} - {"provider"}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(provider=provider, **filtered)


def _ensure_dirs():
    """Create config directories if they don't exist."""
    for d in (CONFIG_DIR, CONVERSATIONS_DIR, SKILLS_DIR, USER_TOOLS_DIR, HOOKS_DIR):
        os.makedirs(d, exist_ok=True)


def load_config() -> AppConfig:
    """Load configuration from disk. Returns defaults if file doesn't exist."""
    _ensure_dirs()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return AppConfig.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    return AppConfig()


def save_config(config: AppConfig):
    """Save configuration to disk."""
    _ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.to_dict(), f, indent=2)


# Singleton config instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the current configuration (lazy-loaded singleton)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def save_current_config():
    """Save the current singleton config to disk."""
    if _config is not None:
        save_config(_config)


def reload_config():
    """Force reload configuration from disk."""
    global _config
    _config = load_config()
