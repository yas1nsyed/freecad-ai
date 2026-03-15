"""Tests for the hooks system."""
import os
from freecad_ai.hooks.registry import HookRegistry


class TestHookRegistry:
    def test_init_empty(self, tmp_path, monkeypatch):
        import freecad_ai.hooks.registry as hooks_mod
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(tmp_path / "nonexistent"))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "nonexistent2"))
        reg = HookRegistry()
        assert reg.discovered_hooks == []

    def test_discovers_hook(self, tmp_path, monkeypatch):
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "my-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_post_tool_use(context):\n    pass\n")
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert hooks[0]["name"] == "my-hook"
        assert "post_tool_use" in hooks[0]["events"]

    def test_skips_disabled_hook(self, tmp_path, monkeypatch):
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "disabled-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_post_response(context):\n    pass\n")
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: ["disabled-hook"])
        reg = HookRegistry()
        assert reg.discovered_hooks == []

    def test_skips_non_callable(self, tmp_path, monkeypatch):
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "bad-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text("on_pre_tool_use = 'not a function'\n")
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert hooks[0]["events"] == []

    def test_syntax_error_in_hook(self, tmp_path, monkeypatch):
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "broken-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text("def on_pre_tool_use(:\n")
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert hooks[0]["has_error"] is True

    def test_multiple_events_in_one_hook(self, tmp_path, monkeypatch):
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "multi-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_pre_tool_use(context):\n    pass\n\n"
            "def on_post_tool_use(context):\n    pass\n")
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert "pre_tool_use" in hooks[0]["events"]
        assert "post_tool_use" in hooks[0]["events"]
