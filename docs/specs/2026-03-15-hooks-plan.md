# Hooks System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** User-defined Python hooks that fire on lifecycle events (pre_tool_use, post_tool_use, user_prompt_submit, post_response) with blocking, modification, and logging capabilities.

**Architecture:** Directory-based discovery (`~/.config/FreeCAD/FreeCADAI/hooks/<name>/hook.py`) with `on_<event>` functions. A `HookRegistry` singleton discovers and fires hooks. Built-in hooks ship in the repo's `hooks/` directory. Integration at 4 points in `chat_widget.py`.

**Tech Stack:** Python 3.11, PySide2, zero external dependencies.

**Spec:** `docs/specs/2026-03-15-hooks-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `freecad_ai/hooks/__init__.py` | **NEW** -- `fire_hook()`, `get_hook_registry()` singleton |
| `freecad_ai/hooks/registry.py` | **NEW** -- `HookRegistry`: discovery, loading, firing, reload |
| `hooks/log-tool-calls/hook.py` | **NEW** -- built-in logging hook (example) |
| `freecad_ai/config.py` | **MODIFY** -- add `HOOKS_DIR`, `hooks_disabled` field, add to `_ensure_dirs()` |
| `freecad_ai/ui/chat_widget.py` | **MODIFY** -- add `fire_hook()` calls at 4 integration points, eager registry init |
| `freecad_ai/ui/settings_dialog.py` | **MODIFY** -- add Hooks group (list, add, edit, remove, reload) |
| `tests/unit/test_hooks.py` | **NEW** -- tests for registry, firing, blocking, chaining, error handling |

---

## Chunk 1: Core -- HookRegistry and Config

### Task 1: Add HOOKS_DIR and hooks_disabled to config

**Files:**
- Modify: `freecad_ai/config.py`

- [ ] **Step 1: Add HOOKS_DIR constant**

After `USER_TOOLS_DIR` (line 15), add:

```python
HOOKS_DIR = os.path.join(CONFIG_DIR, "hooks")
```

- [ ] **Step 2: Add to _ensure_dirs()**

In `_ensure_dirs()` (line 105), add `HOOKS_DIR` to the tuple:

```python
for d in (CONFIG_DIR, CONVERSATIONS_DIR, SKILLS_DIR, USER_TOOLS_DIR, HOOKS_DIR):
```

- [ ] **Step 3: Add hooks_disabled field to AppConfig**

After `scan_freecad_macros` (line 77), add:

```python
hooks_disabled: list = field(default_factory=list)
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass (397+)

- [ ] **Step 5: Commit**

```
git add freecad_ai/config.py
git commit -m "feat: add HOOKS_DIR and hooks_disabled config"
```

---

### Task 2: Create HookRegistry

**Files:**
- Create: `freecad_ai/hooks/__init__.py`
- Create: `freecad_ai/hooks/registry.py`
- Test: `tests/unit/test_hooks.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_hooks.py`:

```python
"""Tests for the hooks system."""
import os
from freecad_ai.hooks.registry import HookRegistry


class TestHookRegistry:
    def test_init_empty(self, tmp_path, monkeypatch):
        """Registry with no hooks dir loads without error."""
        import freecad_ai.hooks.registry as hooks_mod
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(tmp_path / "nonexistent"))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "nonexistent2"))
        reg = HookRegistry()
        assert reg.discovered_hooks == []

    def test_discovers_hook(self, tmp_path, monkeypatch):
        """Registry discovers a hook.py with on_* functions."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "my-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_post_tool_use(context):\n    pass\n"
        )
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])

        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert hooks[0]["name"] == "my-hook"
        assert "post_tool_use" in hooks[0]["events"]

    def test_skips_disabled_hook(self, tmp_path, monkeypatch):
        """Disabled hooks are not loaded."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "disabled-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_post_response(context):\n    pass\n"
        )
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: ["disabled-hook"])

        reg = HookRegistry()
        assert reg.discovered_hooks == []

    def test_skips_non_callable(self, tmp_path, monkeypatch):
        """Non-callable on_* attributes are ignored."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "bad-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "on_pre_tool_use = 'I am a string'\n"
        )
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])

        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert hooks[0]["events"] == []  # no callable events

    def test_syntax_error_in_hook(self, tmp_path, monkeypatch):
        """Hook with syntax error is tracked as error, not crash."""
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
        """A hook can handle multiple events."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "multi-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_pre_tool_use(context):\n    pass\n\n"
            "def on_post_tool_use(context):\n    pass\n"
        )
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])

        reg = HookRegistry()
        hooks = reg.discovered_hooks
        assert len(hooks) == 1
        assert "pre_tool_use" in hooks[0]["events"]
        assert "post_tool_use" in hooks[0]["events"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_hooks.py -v`
Expected: FAIL -- module does not exist

- [ ] **Step 3: Create freecad_ai/hooks/__init__.py**

```python
"""Hooks system for FreeCAD AI.

Provides lifecycle event hooks that users can define to inspect, modify,
or block actions in the workbench.
"""
from .registry import HookRegistry

_registry = None


def get_hook_registry() -> HookRegistry:
    """Return the singleton HookRegistry (created on first call)."""
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry


def fire_hook(event: str, context: dict) -> dict:
    """Fire a hook event and return the merged result."""
    return get_hook_registry().fire(event, context)
```

- [ ] **Step 4: Create freecad_ai/hooks/registry.py**

```python
"""Hook registry -- discovers, loads, and fires user-defined hooks.

Hooks are Python modules in named directories under HOOKS_DIR or
BUILTIN_HOOKS_DIR. Each hook.py defines on_<event> functions that
are called when the corresponding event fires.
"""
import importlib.util
import logging
import os

logger = logging.getLogger(__name__)

from ..config import CONFIG_DIR

HOOKS_DIR = os.path.join(CONFIG_DIR, "hooks")

# Built-in hooks directory (in the repo, alongside freecad_ai/)
BUILTIN_HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "hooks",
)

VALID_EVENTS = ("pre_tool_use", "post_tool_use", "user_prompt_submit", "post_response")


def _get_disabled() -> list:
    """Return list of disabled hook names from config."""
    try:
        from ..config import get_config
        return get_config().hooks_disabled
    except Exception:
        return []


class HookRegistry:
    """Discovers hook directories and loads hook.py modules."""

    def __init__(self):
        self._hooks: dict[str, list[tuple[str, callable]]] = {}
        self._hook_info: list[dict] = []  # for Settings UI
        self._load_hooks()

    def _load_hooks(self):
        """Scan hook directories and register on_* handlers."""
        hooks = {}
        info = []
        disabled = _get_disabled()

        for hooks_dir in (BUILTIN_HOOKS_DIR, HOOKS_DIR):
            if not os.path.isdir(hooks_dir):
                continue
            for entry in sorted(os.listdir(hooks_dir)):
                hook_dir = os.path.join(hooks_dir, entry)
                hook_file = os.path.join(hook_dir, "hook.py")
                if not os.path.isdir(hook_dir) or not os.path.isfile(hook_file):
                    continue
                if entry in disabled:
                    continue
                # Skip if already registered (user overrides built-in)
                if any(h["name"] == entry for h in info):
                    continue

                hook_info = {
                    "name": entry,
                    "path": hook_dir,
                    "events": [],
                    "has_error": False,
                    "error_message": "",
                    "builtin": hooks_dir == BUILTIN_HOOKS_DIR,
                }

                try:
                    spec = importlib.util.spec_from_file_location(
                        f"hook_{entry}", hook_file
                    )
                    if not spec or not spec.loader:
                        hook_info["has_error"] = True
                        hook_info["error_message"] = "Failed to create module spec"
                        info.append(hook_info)
                        continue

                    module = importlib.util.module_from_spec(spec)
                    # Do NOT add to sys.modules — ensures clean reload
                    spec.loader.exec_module(module)

                    for event in VALID_EVENTS:
                        func_name = f"on_{event}"
                        func = getattr(module, func_name, None)
                        if func is not None and callable(func):
                            if event not in hooks:
                                hooks[event] = []
                            hooks[event].append((entry, func))
                            hook_info["events"].append(event)

                except Exception as e:
                    hook_info["has_error"] = True
                    hook_info["error_message"] = str(e)
                    logger.error("Failed to load hook '%s': %s", entry, e)

                info.append(hook_info)

        self._hooks = hooks
        self._hook_info = info

    def fire(self, event: str, context: dict) -> dict:
        """Fire an event. Returns merged result from all hooks.

        For blocking events (pre_tool_use, user_prompt_submit):
            block=True stops immediately.
        For modify (user_prompt_submit):
            modifications chain -- each hook sees previous output.
        Exceptions are caught per-hook and logged.
        """
        handlers = self._hooks.get(event, [])
        if not handlers:
            return {}

        merged = {}
        for hook_name, handler in handlers:
            # Apply previous text modifications to context
            if "modify" in merged and "text" in context:
                context["text"] = merged["modify"]
            try:
                result = handler(context)
            except Exception as e:
                logger.error("Hook '%s' raised %s in %s: %s",
                             hook_name, type(e).__name__, event, e)
                continue
            if result and isinstance(result, dict):
                if result.get("block"):
                    return result  # block wins immediately
                merged.update(result)
        return merged

    def reload(self):
        """Re-scan and reload all hooks. Thread-safe via atomic replacement."""
        old_hooks = self._hooks
        old_info = self._hook_info
        try:
            self._load_hooks()
        except Exception as e:
            logger.error("Hook reload failed: %s", e)
            self._hooks = old_hooks
            self._hook_info = old_info

    @property
    def discovered_hooks(self) -> list[dict]:
        """Return hook info dicts for Settings UI."""
        return list(self._hook_info)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_hooks.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```
git add freecad_ai/hooks/__init__.py freecad_ai/hooks/registry.py tests/unit/test_hooks.py freecad_ai/config.py
git commit -m "feat: add HookRegistry with discovery, loading, and firing"
```

---

### Task 3: Add fire() tests for blocking, modifying, and error handling

**Files:**
- Modify: `tests/unit/test_hooks.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_hooks.py`:

```python
class TestHookFiring:
    def _make_registry(self, tmp_path, monkeypatch, hook_code):
        """Helper: create a registry with a single hook."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        hook_dir = hooks_dir / "test-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(hook_code)
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        return HookRegistry()

    def test_fire_no_hooks(self, tmp_path, monkeypatch):
        """Firing an event with no hooks returns empty dict."""
        reg = self._make_registry(tmp_path, monkeypatch,
            "def on_post_response(context):\n    pass\n")
        result = reg.fire("pre_tool_use", {"tool_name": "test"})
        assert result == {}

    def test_fire_blocking_hook(self, tmp_path, monkeypatch):
        """A hook that returns block=True blocks the action."""
        reg = self._make_registry(tmp_path, monkeypatch,
            "def on_pre_tool_use(context):\n"
            "    if context['tool_name'] == 'dangerous':\n"
            "        return {'block': True, 'reason': 'Too dangerous'}\n"
            "    return {}\n"
        )
        result = reg.fire("pre_tool_use", {"tool_name": "dangerous"})
        assert result["block"] is True
        assert "dangerous" in result["reason"]

        result2 = reg.fire("pre_tool_use", {"tool_name": "safe_tool"})
        assert result2.get("block") is not True

    def test_fire_modify_hook(self, tmp_path, monkeypatch):
        """A hook can modify the user's text."""
        reg = self._make_registry(tmp_path, monkeypatch,
            "def on_user_prompt_submit(context):\n"
            "    return {'modify': context['text'].upper()}\n"
        )
        result = reg.fire("user_prompt_submit",
                          {"text": "hello", "images": [], "mode": "act"})
        assert result["modify"] == "HELLO"

    def test_fire_exception_continues(self, tmp_path, monkeypatch):
        """A hook that raises does not crash, other hooks still run."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        # Hook A: crashes
        hook_a = hooks_dir / "a-crasher"
        hook_a.mkdir()
        (hook_a / "hook.py").write_text(
            "def on_post_tool_use(context):\n    raise RuntimeError('boom')\n"
        )

        # Hook B: works (alphabetically after A)
        hook_b = hooks_dir / "b-logger"
        hook_b.mkdir()
        (hook_b / "hook.py").write_text(
            "results = []\n"
            "def on_post_tool_use(context):\n"
            "    results.append(context['tool_name'])\n"
        )

        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()

        # Should not raise even though hook A crashes
        reg.fire("post_tool_use", {
            "tool_name": "test", "arguments": {},
            "success": True, "output": "", "error": "", "turn": 1,
        })

    def test_fire_block_wins_over_modify(self, tmp_path, monkeypatch):
        """If one hook blocks, modification from earlier hook is ignored."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        # Hook A: modifies (alphabetically first)
        hook_a = hooks_dir / "a-modifier"
        hook_a.mkdir()
        (hook_a / "hook.py").write_text(
            "def on_user_prompt_submit(context):\n"
            "    return {'modify': 'modified text'}\n"
        )

        # Hook B: blocks (alphabetically second)
        hook_b = hooks_dir / "b-blocker"
        hook_b.mkdir()
        (hook_b / "hook.py").write_text(
            "def on_user_prompt_submit(context):\n"
            "    return {'block': True, 'reason': 'nope'}\n"
        )

        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()

        result = reg.fire("user_prompt_submit",
                          {"text": "hello", "images": [], "mode": "act"})
        assert result.get("block") is True

    def test_fire_modify_chains(self, tmp_path, monkeypatch):
        """Multiple modify hooks chain: each sees previous output."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        hook_a = hooks_dir / "a-upper"
        hook_a.mkdir()
        (hook_a / "hook.py").write_text(
            "def on_user_prompt_submit(context):\n"
            "    return {'modify': context['text'].upper()}\n"
        )

        hook_b = hooks_dir / "b-exclaim"
        hook_b.mkdir()
        (hook_b / "hook.py").write_text(
            "def on_user_prompt_submit(context):\n"
            "    return {'modify': context['text'] + '!'}\n"
        )

        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])
        reg = HookRegistry()

        result = reg.fire("user_prompt_submit",
                          {"text": "hello", "images": [], "mode": "act"})
        assert result["modify"] == "HELLO!"

    def test_reload_picks_up_new_hooks(self, tmp_path, monkeypatch):
        """Reload discovers newly added hooks."""
        import freecad_ai.hooks.registry as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr(hooks_mod, "HOOKS_DIR", str(hooks_dir))
        monkeypatch.setattr(hooks_mod, "BUILTIN_HOOKS_DIR", str(tmp_path / "empty"))
        monkeypatch.setattr(hooks_mod, "_get_disabled", lambda: [])

        reg = HookRegistry()
        assert reg.discovered_hooks == []

        # Add a hook after creation
        hook_dir = hooks_dir / "new-hook"
        hook_dir.mkdir()
        (hook_dir / "hook.py").write_text(
            "def on_post_response(context):\n    pass\n"
        )
        reg.reload()
        assert len(reg.discovered_hooks) == 1
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_hooks.py -v`
Expected: PASS (13 tests total)

- [ ] **Step 3: Commit**

```
git add tests/unit/test_hooks.py
git commit -m "test: add hook firing tests for blocking, modifying, chaining, errors"
```

---

### Task 4: Create built-in log-tool-calls hook

**Files:**
- Create: `hooks/log-tool-calls/hook.py`

- [ ] **Step 1: Create the hook**

Create `hooks/log-tool-calls/hook.py`:

```python
"""Log all tool calls to the FreeCAD report view.

Built-in hook that logs each tool execution with its name, success status,
and any error message. Useful for debugging skill and tool issues.
"""
import logging

logger = logging.getLogger("freecad_ai.hooks.log_tool_calls")


def on_post_tool_use(context):
    """Log tool call results."""
    level = logging.INFO if context["success"] else logging.WARNING
    msg = "Tool: %s | success=%s"
    args = [context["tool_name"], context["success"]]
    if context.get("error"):
        msg += " | error=%s"
        args.append(context["error"])
    logger.log(level, msg, *args)
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```
git add hooks/log-tool-calls/hook.py
git commit -m "feat: add built-in log-tool-calls hook"
```

---

## Chunk 2: Integration -- Wire fire_hook into chat_widget.py

### Task 5: Add fire_hook calls to chat_widget.py

**Files:**
- Modify: `freecad_ai/ui/chat_widget.py`

- [ ] **Step 1: Add eager registry init in ChatDockWidget.__init__**

After `self._optimization_active = False` (line 505), add:

```python
# Initialize hook registry on main thread (before any worker threads)
from ..hooks import get_hook_registry
get_hook_registry()
```

- [ ] **Step 2: Add user_prompt_submit hook in _send_message**

In `_send_message()`, after skill command handling (line 659) and before image collection, add:

```python
# Fire user_prompt_submit hook
from ..hooks import fire_hook
mode = "plan" if self.mode_combo.currentIndex() == 0 else "act"
hook_result = fire_hook("user_prompt_submit", {
    "text": text, "images": [], "mode": mode,
})
if hook_result.get("block"):
    self._append_html(render_message("system",
        f"Blocked by hook: {hook_result.get('reason', 'no reason given')}"))
    return
if hook_result.get("modify"):
    text = hook_result["modify"]
```

Place this after the skill command check (line 659) but before the vision/image handling (line 661).

- [ ] **Step 3: Add pre_tool_use and post_tool_use hooks in _LLMWorker._tool_loop**

In the `for tc in tool_calls:` loop (line 199), wrap the existing tool execution:

```python
for tc in tool_calls:
    # Pre-tool-use hook
    from ..hooks import fire_hook
    hook_result = fire_hook("pre_tool_use", {
        "tool_name": tc.name,
        "arguments": tc.arguments,
        "turn": turn,
    })
    if hook_result.get("block"):
        result = {"success": False, "output": "",
                  "error": f"Blocked by hook: {hook_result.get('reason', '')}"}
    elif tc.name == "optimize_iteration" and self.registry:
        # existing optimize_iteration code
        tr = self.registry.execute(tc.name, tc.arguments)
        result = {"success": tr.success, "output": tr.output, "error": tr.error}
    else:
        result = self._execute_tool_on_main_thread(tc.name, tc.arguments)

    success = result.get("success", False)
    output = result.get("output", "")
    error = result.get("error", "")
    result_text = output if success else f"Error: {error}"

    self.tool_call_finished.emit(tc.name, tc.id, success, result_text)

    # Post-tool-use hook
    fire_hook("post_tool_use", {
        "tool_name": tc.name,
        "arguments": tc.arguments,
        "success": success,
        "output": output,
        "error": error,
        "turn": turn,
    })
```

- [ ] **Step 4: Add post_response hook in _on_response_finished**

In `_on_response_finished()`, after `self.conversation.save()` (line 1291), add:

```python
# Post-response hook
from ..hooks import fire_hook
fire_hook("post_response", {
    "response_text": full_response,
    "tool_calls_count": len(self._worker._tool_results) if self._worker and self._worker._tool_results else 0,
    "mode": "plan" if self.mode_combo.currentIndex() == 0 else "act",
})
```

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```
git add freecad_ai/ui/chat_widget.py
git commit -m "feat: wire fire_hook into chat_widget at 4 integration points"
```

---

## Chunk 3: Settings UI

### Task 6: Add Hooks group to Settings dialog

**Files:**
- Modify: `freecad_ai/ui/settings_dialog.py`

- [ ] **Step 1: Add Hooks group after User Tools group**

After `layout.addWidget(user_tools_group)` (line 290), add:

```python
# Hooks group
hooks_group = QGroupBox(translate("SettingsDialog", "Hooks"))
hooks_layout = QVBoxLayout()

self.hooks_list = QListWidget()
self.hooks_list.setMaximumHeight(100)
hooks_layout.addWidget(self.hooks_list)

hooks_btn_layout = QHBoxLayout()
hooks_add_btn = QPushButton(translate("SettingsDialog", "Add..."))
hooks_add_btn.clicked.connect(self._add_hook)
hooks_btn_layout.addWidget(hooks_add_btn)

hooks_edit_btn = QPushButton(translate("SettingsDialog", "Edit..."))
hooks_edit_btn.clicked.connect(self._edit_hook)
hooks_btn_layout.addWidget(hooks_edit_btn)

hooks_remove_btn = QPushButton(translate("SettingsDialog", "Remove"))
hooks_remove_btn.clicked.connect(self._remove_hook)
hooks_btn_layout.addWidget(hooks_remove_btn)

hooks_reload_btn = QPushButton(translate("SettingsDialog", "Reload"))
hooks_reload_btn.clicked.connect(self._reload_hooks)
hooks_btn_layout.addWidget(hooks_reload_btn)

hooks_btn_layout.addStretch()
hooks_layout.addLayout(hooks_btn_layout)

hooks_group.setLayout(hooks_layout)
layout.addWidget(hooks_group)
```

- [ ] **Step 2: Add hooks list population in _load_from_config**

In `_load_from_config()`, add:

```python
# Hooks
self.hooks_list.clear()
from ..hooks import get_hook_registry
for hook in get_hook_registry().discovered_hooks:
    if hook["has_error"]:
        label = f"\u2717 {hook['name']} ({hook['error_message'][:50]})"
    else:
        events = ", ".join(hook["events"])
        label = f"\u2713 {hook['name']} ({events})"
    self.hooks_list.addItem(label)
```

- [ ] **Step 3: Add hooks config save in _save**

In `_save()`, add:

```python
# hooks_disabled is managed by add/remove, already in config
```

Actually, `hooks_disabled` is already saved via the config — no extra save logic needed. The list is visual only (shows what's loaded).

- [ ] **Step 4: Add hook management methods**

```python
def _add_hook(self):
    """Add a hook by copying a hook.py file into a new directory."""
    from ..config import HOOKS_DIR
    path, _ = QFileDialog.getOpenFileName(
        self, translate("SettingsDialog", "Select hook.py file"), "",
        translate("SettingsDialog", "Python files (*.py)"))
    if not path:
        return
    # Ask for hook name
    name, ok = QtWidgets.QInputDialog.getText(
        self, translate("SettingsDialog", "Hook Name"),
        translate("SettingsDialog", "Enter a name for this hook:"))
    if not ok or not name.strip():
        return
    name = name.strip().lower().replace(" ", "-")
    hook_dir = os.path.join(HOOKS_DIR, name)
    os.makedirs(hook_dir, exist_ok=True)
    import shutil
    shutil.copy2(path, os.path.join(hook_dir, "hook.py"))
    self._reload_hooks()

def _edit_hook(self):
    """Open the selected hook's hook.py in the default editor."""
    row = self.hooks_list.currentRow()
    if row < 0:
        return
    from ..hooks import get_hook_registry
    hooks = get_hook_registry().discovered_hooks
    if row >= len(hooks):
        return
    hook_path = os.path.join(hooks[row]["path"], "hook.py")
    from ..ui.compat import QtCore
    url = QtCore.QUrl.fromLocalFile(hook_path)
    from ..ui.compat import QtGui
    QtGui.QDesktopServices.openUrl(url)

def _remove_hook(self):
    """Remove the selected hook directory."""
    row = self.hooks_list.currentRow()
    if row < 0:
        return
    from ..hooks import get_hook_registry
    hooks = get_hook_registry().discovered_hooks
    if row >= len(hooks):
        return
    hook = hooks[row]
    if hook.get("builtin"):
        QMessageBox.information(
            self, translate("SettingsDialog", "Cannot Remove"),
            translate("SettingsDialog",
                      "Built-in hooks cannot be removed. You can disable them instead."))
        return
    reply = QMessageBox.question(
        self, translate("SettingsDialog", "Remove Hook"),
        translate("SettingsDialog", f"Remove hook '{hook['name']}'?"))
    if reply != QMessageBox.Yes:
        return
    import shutil
    shutil.rmtree(hook["path"], ignore_errors=True)
    self._reload_hooks()

def _reload_hooks(self):
    """Reload all hooks and refresh the list."""
    from ..hooks import get_hook_registry
    get_hook_registry().reload()
    # Refresh list
    self.hooks_list.clear()
    for hook in get_hook_registry().discovered_hooks:
        if hook["has_error"]:
            label = f"\u2717 {hook['name']} ({hook['error_message'][:50]})"
        else:
            events = ", ".join(hook["events"])
            label = f"\u2713 {hook['name']} ({events})"
        self.hooks_list.addItem(label)
```

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/unit/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```
git add freecad_ai/ui/settings_dialog.py
git commit -m "feat: add Hooks group to Settings dialog"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Update CHANGELOG.md**

Add under `[Unreleased] > Added`:

```markdown
- **Hooks system** -- user-defined Python hooks that fire on lifecycle events (`pre_tool_use`, `post_tool_use`, `user_prompt_submit`, `post_response`). Hooks can block actions, modify input, or log activity. Directory-based discovery at `~/.config/FreeCAD/FreeCADAI/hooks/`. Includes built-in `log-tool-calls` hook and Settings UI for managing hooks.
```

- [ ] **Step 2: Update README.md**

Add to features list:

```markdown
- **Hooks** -- user-defined Python hooks for lifecycle events (block tools, modify input, log activity)
```

- [ ] **Step 3: Commit**

```
git add CHANGELOG.md README.md
git commit -m "docs: add hooks system to changelog and readme"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| **1: Core** | 1--4 | `HookRegistry` with discovery, loading, firing, tests, built-in hook, config |
| **2: Integration** | 5 | `fire_hook()` wired into chat_widget at 4 lifecycle points |
| **3: UI + Docs** | 6--7 | Settings dialog Hooks group, changelog, readme |

Total: 7 tasks across 3 chunks. Each chunk produces testable, committable code.
