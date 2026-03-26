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


import os
