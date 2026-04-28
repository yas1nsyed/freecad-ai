"""Tests for configuration system."""

import json

import pytest

from freecad_ai.config import (
    PROVIDER_PRESETS,
    AppConfig,
    ProviderConfig,
    get_config,
    load_config,
    reload_config,
    save_config,
    save_current_config,
)


class TestProviderConfig:
    def test_defaults(self):
        p = ProviderConfig()
        assert p.name == "anthropic"
        assert p.api_key == ""
        assert "anthropic" in p.base_url
        assert "claude" in p.model

    def test_apply_preset_ollama(self):
        p = ProviderConfig()
        p.apply_preset("ollama")
        assert p.name == "ollama"
        assert "localhost" in p.base_url
        assert p.model == "llama3"

    def test_apply_preset_openai(self):
        p = ProviderConfig()
        p.apply_preset("openai")
        assert p.name == "openai"
        assert "openai.com" in p.base_url

    def test_apply_preset_custom(self):
        p = ProviderConfig()
        p.apply_preset("custom")
        assert p.name == "custom"
        assert p.base_url == ""

    def test_apply_unknown_preset_keeps_existing(self):
        p = ProviderConfig(base_url="http://example.com", model="my-model")
        p.apply_preset("nonexistent")
        assert p.base_url == "http://example.com"
        assert p.model == "my-model"


class TestAppConfig:
    def test_defaults(self):
        c = AppConfig()
        assert c.mode == "plan"
        assert c.max_tokens == 4096
        assert c.temperature == 0.3
        assert c.auto_execute is False
        assert c.enable_tools is True
        assert c.thinking == "off"
        assert c.mcp_servers == []

    def test_to_dict_roundtrip(self):
        c = AppConfig()
        c.provider.apply_preset("ollama")
        c.max_tokens = 8192
        c.mcp_servers = [{"name": "test", "command": "echo"}]
        d = c.to_dict()
        c2 = AppConfig.from_dict(d)
        assert c2.provider.name == "ollama"
        assert c2.max_tokens == 8192
        assert len(c2.mcp_servers) == 1

    def test_from_dict_ignores_unknown_keys(self):
        d = {
            "provider": {"name": "anthropic", "api_key": "", "base_url": "", "model": ""},
            "unknown_field": "should be ignored",
            "mode": "act",
        }
        c = AppConfig.from_dict(d)
        assert c.mode == "act"
        assert not hasattr(c, "unknown_field")

    def test_from_dict_handles_empty_provider(self):
        d = {"mode": "plan"}
        c = AppConfig.from_dict(d)
        assert c.provider.name == "anthropic"  # default

    def test_from_dict_preserves_all_fields(self):
        original = AppConfig()
        original.mode = "act"
        original.temperature = 0.7
        original.thinking = "on"
        d = original.to_dict()
        restored = AppConfig.from_dict(d)
        assert restored.mode == "act"
        assert restored.temperature == 0.7
        assert restored.thinking == "on"

    def test_chat_dock_state_defaults(self):
        c = AppConfig()
        assert c.chat_dock_floating is False
        assert c.chat_dock_area == "right"
        assert c.chat_dock_geometry == []
        assert c.chat_dock_tabified_with == []
        assert c.chat_dock_mw_state == ""

    def test_chat_dock_state_roundtrip(self):
        c = AppConfig()
        c.chat_dock_floating = True
        c.chat_dock_area = "left"
        c.chat_dock_geometry = [100, 200, 400, 600]
        c.chat_dock_tabified_with = ["Tasks", "ModelView"]
        c.chat_dock_mw_state = "aGVsbG8gd29ybGQ="  # base64 placeholder
        d = c.to_dict()
        c2 = AppConfig.from_dict(d)
        assert c2.chat_dock_floating is True
        assert c2.chat_dock_area == "left"
        assert c2.chat_dock_geometry == [100, 200, 400, 600]
        assert c2.chat_dock_tabified_with == ["Tasks", "ModelView"]
        assert c2.chat_dock_mw_state == "aGVsbG8gd29ybGQ="


class TestProviderPresets:
    def test_all_presets_have_required_keys(self):
        for name, preset in PROVIDER_PRESETS.items():
            assert "base_url" in preset, f"{name} missing base_url"
            assert "default_model" in preset, f"{name} missing default_model"

    def test_known_presets_exist(self):
        from freecad_ai.llm.providers import PROVIDERS
        # PROVIDER_PRESETS should have exactly the same keys as PROVIDERS
        assert set(PROVIDER_PRESETS.keys()) == set(PROVIDERS.keys())


class TestSaveLoad:
    def test_save_and_load(self, tmp_config_dir):
        c = AppConfig()
        c.provider.apply_preset("ollama")
        c.max_tokens = 2048
        save_config(c)

        loaded = load_config()
        assert loaded.provider.name == "ollama"
        assert loaded.max_tokens == 2048

    def test_load_returns_defaults_when_no_file(self, tmp_config_dir):
        c = load_config()
        assert c.mode == "plan"
        assert c.provider.name == "anthropic"

    def test_load_returns_defaults_on_corrupt_json(self, tmp_config_dir):
        import freecad_ai.config as config_mod
        config_file = config_mod.CONFIG_FILE
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, "w") as f:
            f.write("not valid json {{{")

        c = load_config()
        assert c.mode == "plan"  # defaults

    def test_load_returns_defaults_on_bad_types(self, tmp_config_dir):
        import freecad_ai.config as config_mod
        config_file = config_mod.CONFIG_FILE
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, "w") as f:
            json.dump({"provider": "not a dict"}, f)

        c = load_config()
        assert isinstance(c, AppConfig)


class TestSingleton:
    def test_get_config_returns_same_instance(self, tmp_config_dir):
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_reload_config_creates_new_instance(self, tmp_config_dir):
        c1 = get_config()
        reload_config()
        c2 = get_config()
        assert c1 is not c2

    def test_save_current_config_writes_singleton(self, tmp_config_dir):
        c = get_config()
        c.mode = "act"
        save_current_config()

        loaded = load_config()
        assert loaded.mode == "act"

    def test_save_current_config_noop_when_no_singleton(self, tmp_config_dir):
        import freecad_ai.config as config_mod
        config_mod._config = None
        save_current_config()  # Should not raise


class TestParamStoreBridge:
    """Bridge between FreeCAD's BaseApp/Preferences/Mod/FreeCADAI store and AppConfig."""

    def _fake_param_group(self, ints=None, strings=None, bools=None):
        """Mimic the relevant parts of a FreeCAD ParamGet group object."""
        ints = dict(ints or {})
        strings = dict(strings or {})
        bools = dict(bools or {})

        class _FakeGroup:
            def GetInts(_self):  # noqa: N802 — mimicking FreeCAD camelCase
                return list(ints.keys())
            def GetStrings(_self):
                return list(strings.keys())
            def GetBools(_self):
                return list(bools.keys())
            def GetInt(_self, key, default=0):
                return ints.get(key, default)
            def GetString(_self, key, default=""):
                return strings.get(key, default)
            def GetBool(_self, key, default=False):
                return bools.get(key, default)
            def SetInt(_self, key, value):
                ints[key] = value
            def SetString(_self, key, value):
                strings[key] = value
            def SetBool(_self, key, value):
                bools[key] = value

        return _FakeGroup(), ints, strings, bools

    def test_overrides_skipped_when_param_store_unavailable(self):
        """Outside FreeCAD, _get_param_group returns None — cfg unchanged."""
        from freecad_ai.config import AppConfig, _apply_param_store_overrides
        cfg = AppConfig()
        cfg.provider.name = "anthropic"
        _apply_param_store_overrides(cfg)  # no FreeCAD → no-op
        assert cfg.provider.name == "anthropic"

    def test_apply_overrides_provider_index(self):
        from freecad_ai.config import AppConfig, _apply_param_store_overrides
        from unittest.mock import patch
        cfg = AppConfig()
        cfg.provider.name = "anthropic"
        group, _, _, _ = self._fake_param_group(ints={"ProviderIndex": 2})  # ollama
        with patch("freecad_ai.config._get_param_group", return_value=group):
            _apply_param_store_overrides(cfg)
        assert cfg.provider.name == "ollama"

    def test_apply_overrides_strings(self):
        from freecad_ai.config import AppConfig, _apply_param_store_overrides
        from unittest.mock import patch
        cfg = AppConfig()
        group, _, _, _ = self._fake_param_group(strings={
            "Model": "qwen3-vl:32b",
            "BaseUrl": "http://spark:11434/v1",
            "ApiKey": "cmd:secret-tool lookup service freecad-ai",
        })
        with patch("freecad_ai.config._get_param_group", return_value=group):
            _apply_param_store_overrides(cfg)
        assert cfg.provider.model == "qwen3-vl:32b"
        assert cfg.provider.base_url == "http://spark:11434/v1"
        assert cfg.provider.api_key == "cmd:secret-tool lookup service freecad-ai"

    def test_apply_overrides_bool_and_int(self):
        from freecad_ai.config import AppConfig, _apply_param_store_overrides
        from unittest.mock import patch
        cfg = AppConfig()
        cfg.enable_tools = True
        cfg.max_tokens = 4096
        group, _, _, _ = self._fake_param_group(
            bools={"EnableTools": False},
            ints={"MaxTokens": 8192, "ModeIndex": 1, "ThinkingIndex": 2},
        )
        with patch("freecad_ai.config._get_param_group", return_value=group):
            _apply_param_store_overrides(cfg)
        assert cfg.enable_tools is False
        assert cfg.max_tokens == 8192
        assert cfg.mode == "act"
        assert cfg.thinking == "extended"

    def test_apply_overrides_skips_untouched_keys(self):
        """Param store with no relevant keys → cfg untouched."""
        from freecad_ai.config import AppConfig, _apply_param_store_overrides
        from unittest.mock import patch
        cfg = AppConfig()
        cfg.provider.name = "anthropic"
        cfg.max_tokens = 4096
        group, _, _, _ = self._fake_param_group()  # all empty
        with patch("freecad_ai.config._get_param_group", return_value=group):
            _apply_param_store_overrides(cfg)
        assert cfg.provider.name == "anthropic"
        assert cfg.max_tokens == 4096

    def test_apply_ignores_out_of_range_index(self):
        """Defensive — corrupt param store with bad enum index leaves cfg alone."""
        from freecad_ai.config import AppConfig, _apply_param_store_overrides
        from unittest.mock import patch
        cfg = AppConfig()
        cfg.mode = "plan"
        group, _, _, _ = self._fake_param_group(ints={"ModeIndex": 99})
        with patch("freecad_ai.config._get_param_group", return_value=group):
            _apply_param_store_overrides(cfg)
        assert cfg.mode == "plan"

    def test_load_config_seeds_empty_param_store_from_json(self, tmp_path, monkeypatch):
        """Regression: Edit → Preferences was showing blank fields when JSON
        had values but the param store was empty (e.g., user upgraded from
        v0.11.x where ParamGet bridge didn't exist). load_config must seed
        the param store from JSON so Gui::Pref* widgets see current values.
        """
        from unittest.mock import patch
        import freecad_ai.config as config_mod

        cfg_dir = tmp_path / "FreeCADAI"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text(json.dumps({
            "provider": {
                "name": "ollama",
                "model": "qwen3-vl:32b",
                "base_url": "http://spark:11434/v1",
                "api_key": "cmd:secret-tool lookup service freecad-ai",
            },
            "mode": "act",
            "thinking": "on",
            "max_tokens": 8192,
            "enable_tools": False,
        }))
        monkeypatch.setattr(config_mod, "CONFIG_FILE", str(cfg_file))
        monkeypatch.setattr(config_mod, "CONFIG_DIR", str(cfg_dir))

        group, ints, strings, bools = self._fake_param_group()  # empty store
        with patch.object(config_mod, "_get_param_group", return_value=group):
            cfg = config_mod.load_config()

        # JSON values land in the in-memory cfg
        assert cfg.provider.name == "ollama"
        assert cfg.provider.model == "qwen3-vl:32b"
        assert cfg.provider.base_url == "http://spark:11434/v1"
        assert cfg.mode == "act"

        # Param store now mirrors JSON — Edit → Preferences will read these
        assert ints.get("ProviderIndex") == config_mod._PARAM_PROVIDERS.index("ollama")
        assert strings.get("Model") == "qwen3-vl:32b"
        assert strings.get("BaseUrl") == "http://spark:11434/v1"
        assert strings.get("ApiKey") == "cmd:secret-tool lookup service freecad-ai"
        assert ints.get("ModeIndex") == config_mod._PARAM_MODES.index("act")
        assert ints.get("ThinkingIndex") == config_mod._PARAM_THINKING.index("on")
        assert ints.get("MaxTokens") == 8192
        assert bools.get("EnableTools") is False

    def test_load_config_param_store_wins_over_json(self, tmp_path, monkeypatch):
        """If the user changed a value in Edit → Preferences (param store)
        and JSON has a different value, the param-store value wins on load.
        After seeding, both surfaces reflect the param-store value.
        """
        from unittest.mock import patch
        import freecad_ai.config as config_mod

        cfg_dir = tmp_path / "FreeCADAI"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text(json.dumps({
            "provider": {"name": "anthropic", "model": "claude-sonnet-4-20250514"},
            "max_tokens": 4096,
        }))
        monkeypatch.setattr(config_mod, "CONFIG_FILE", str(cfg_file))
        monkeypatch.setattr(config_mod, "CONFIG_DIR", str(cfg_dir))

        group, ints, strings, bools = self._fake_param_group(
            ints={"ProviderIndex": config_mod._PARAM_PROVIDERS.index("ollama"), "MaxTokens": 16384},
            strings={"Model": "qwen3-vl:32b"},
        )
        with patch.object(config_mod, "_get_param_group", return_value=group):
            cfg = config_mod.load_config()

        # ParamGet wins — preference page changes survive
        assert cfg.provider.name == "ollama"
        assert cfg.provider.model == "qwen3-vl:32b"
        assert cfg.max_tokens == 16384

    def test_write_to_param_store_round_trips(self):
        """Write then re-apply via overrides — values come back identical."""
        from freecad_ai.config import (
            AppConfig, _apply_param_store_overrides, _write_to_param_store,
        )
        from unittest.mock import patch
        group, ints, strings, bools = self._fake_param_group()

        cfg_out = AppConfig()
        cfg_out.provider.name = "ollama"
        cfg_out.provider.model = "gemma3:4b"
        cfg_out.provider.base_url = "http://spark:11434/v1"
        cfg_out.provider.api_key = "file:/etc/keys/api"
        cfg_out.mode = "act"
        cfg_out.thinking = "on"
        cfg_out.max_tokens = 16384
        cfg_out.enable_tools = False

        with patch("freecad_ai.config._get_param_group", return_value=group):
            _write_to_param_store(cfg_out)

        cfg_in = AppConfig()  # fresh defaults
        with patch("freecad_ai.config._get_param_group", return_value=group):
            _apply_param_store_overrides(cfg_in)

        assert cfg_in.provider.name == "ollama"
        assert cfg_in.provider.model == "gemma3:4b"
        assert cfg_in.provider.base_url == "http://spark:11434/v1"
        assert cfg_in.provider.api_key == "file:/etc/keys/api"
        assert cfg_in.mode == "act"
        assert cfg_in.thinking == "on"
        assert cfg_in.max_tokens == 16384
        assert cfg_in.enable_tools is False


import os
