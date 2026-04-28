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
    # Tool-calling capability (Ollama /api/show "tools"). None=untested or
    # non-Ollama (in which case provider.supports_tools is the source of truth).
    # False explicitly = the model doesn't support tools (e.g. embedding/reranker
    # picked as main model) → suppress tools array in chat sends.
    tools_detected: bool | None = None
    # Thinking capability (Ollama /api/show "thinking"). Diagnostic-only today.
    thinking_detected: bool | None = None

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

    # Chat dock layout persistence. FreeCAD's native mw.restoreState runs
    # before the workbench activates, so our dock misses the restore and
    # lands at its default area every startup. We snapshot our own state
    # on dock-move events and reapply in get_chat_dock().
    chat_dock_floating: bool = False
    chat_dock_area: str = "right"  # "left", "right", "top", "bottom"
    chat_dock_geometry: list = field(default_factory=list)  # [x, y, w, h] when floating
    chat_dock_tabified_with: list = field(default_factory=list)  # sibling objectNames
    # Base64-encoded QMainWindow.saveState() — captures tabification reliably
    # (surgical tabified_with list can miss tabify-by-drag because no Qt signal
    # fires in that case).
    chat_dock_mw_state: str = ""

    @property
    def supports_vision(self) -> bool:
        """Whether the current LLM supports vision (images in content blocks)."""
        if self.vision_override is not None:
            return self.vision_override
        if self.vision_detected is not None:
            return self.vision_detected
        return False

    @property
    def supports_tools(self) -> bool:
        """Whether the current LLM supports tool calling.

        Detected capability (from Ollama /api/show) takes precedence — it
        catches the case where someone picks an embedding/reranker model
        as the main model on a provider that the static table marks as
        tool-capable. Otherwise fall back to the provider-wide flag.
        """
        if self.tools_detected is not None:
            return self.tools_detected
        from .llm.providers import supports_tools as _provider_supports_tools
        return _provider_supports_tools(self.provider.name)

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
    """Load configuration from disk. Returns defaults if file doesn't exist.

    After loading from JSON, layers any values present in FreeCAD's parameter
    store (BaseApp/Preferences/Mod/FreeCADAI) on top — so changes the user
    made via Edit → Preferences propagate to the workbench's settings on
    next load even though they're written by FreeCAD's Pref* widgets.

    Then mirrors the merged result back to the parameter store so the
    Edit → Preferences page (which reads Pref* widgets directly from the
    param store) reflects current values. Without this, users upgrading
    from a version without the bridge would see blank fields in the
    preferences page until they saved through the AI Settings dialog.
    """
    _ensure_dirs()
    cfg = AppConfig()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            cfg = AppConfig.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    _apply_param_store_overrides(cfg)
    _write_to_param_store(cfg)
    return cfg


def save_config(config: AppConfig):
    """Save configuration to disk and mirror to FreeCAD's parameter store."""
    _ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
    _write_to_param_store(config)


# ── FreeCAD parameter-store bridge ──────────────────────────────────────
#
# Edit → Preferences uses Gui::Pref* widgets that auto-save to
# BaseApp/Preferences/Mod/FreeCADAI/. AppConfig stores everything in JSON
# at ~/.config/FreeCAD/FreeCADAI/config.json. We mirror the subset of
# fields exposed in the preferences page so both UIs stay coherent.
#
# Indices stored in the param store correspond to the order of items in
# resources/panels/FreeCADAIPrefs.ui — keep these lists in sync.

_PARAM_PROVIDERS = [
    "anthropic", "openai", "ollama", "gemini", "openrouter",
    "moonshot", "deepseek", "qwen", "groq", "mistral", "together",
]
_PARAM_MODES = ["plan", "act"]
_PARAM_THINKING = ["off", "on", "extended"]


def _get_param_group():
    """Return the FreeCAD ParamGet group, or None when running outside FreeCAD."""
    try:
        import FreeCAD
        return FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCADAI")
    except (ImportError, RuntimeError):
        return None


def _apply_param_store_overrides(cfg: AppConfig) -> None:
    """Layer ParamGet values onto cfg for fields exposed in the prefs page.

    Only overrides when the param store has an explicit value. The Pref*
    widgets only write on first interaction, so an unset key means the user
    hasn't touched the preferences page — JSON value stays authoritative.
    """
    group = _get_param_group()
    if group is None:
        return
    keys = set(group.GetStrings()) | set(group.GetInts()) | set(group.GetBools())

    if "ProviderIndex" in keys:
        idx = group.GetInt("ProviderIndex", 0)
        if 0 <= idx < len(_PARAM_PROVIDERS):
            cfg.provider.name = _PARAM_PROVIDERS[idx]
    if "Model" in keys:
        cfg.provider.model = group.GetString("Model", cfg.provider.model)
    if "BaseUrl" in keys:
        cfg.provider.base_url = group.GetString("BaseUrl", cfg.provider.base_url)
    if "ApiKey" in keys:
        cfg.provider.api_key = group.GetString("ApiKey", cfg.provider.api_key)
    if "ModeIndex" in keys:
        idx = group.GetInt("ModeIndex", 0)
        if 0 <= idx < len(_PARAM_MODES):
            cfg.mode = _PARAM_MODES[idx]
    if "ThinkingIndex" in keys:
        idx = group.GetInt("ThinkingIndex", 0)
        if 0 <= idx < len(_PARAM_THINKING):
            cfg.thinking = _PARAM_THINKING[idx]
    if "MaxTokens" in keys:
        cfg.max_tokens = group.GetInt("MaxTokens", cfg.max_tokens)
    if "EnableTools" in keys:
        cfg.enable_tools = group.GetBool("EnableTools", cfg.enable_tools)


def _write_to_param_store(cfg: AppConfig) -> None:
    """Mirror cfg values to ParamGet so the preferences page reflects them.

    Lets the user open Edit → Preferences after using the Settings dialog
    and see current values rather than stale Pref widget defaults.
    """
    group = _get_param_group()
    if group is None:
        return
    if cfg.provider.name in _PARAM_PROVIDERS:
        group.SetInt("ProviderIndex", _PARAM_PROVIDERS.index(cfg.provider.name))
    group.SetString("Model", cfg.provider.model)
    group.SetString("BaseUrl", cfg.provider.base_url)
    group.SetString("ApiKey", cfg.provider.api_key)
    if cfg.mode in _PARAM_MODES:
        group.SetInt("ModeIndex", _PARAM_MODES.index(cfg.mode))
    if cfg.thinking in _PARAM_THINKING:
        group.SetInt("ThinkingIndex", _PARAM_THINKING.index(cfg.thinking))
    group.SetInt("MaxTokens", int(cfg.max_tokens))
    group.SetBool("EnableTools", bool(cfg.enable_tools))


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
