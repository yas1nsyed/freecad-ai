# Hooks System — Design Spec

**Date**: 2026-03-15
**Status**: Draft

## Overview

User-defined Python hooks that fire on lifecycle events in the FreeCAD AI workbench. Hooks can inspect context, log activity, block dangerous operations, or modify user input. Each hook is a named directory containing a `hook.py` file with `on_<event>` handler functions.

## Hook Structure

```
~/.config/FreeCAD/FreeCADAI/hooks/
├── safety-guard/
│   └── hook.py
├── auto-screenshot/
│   └── hook.py
└── my-logger/
    └── hook.py
```

Built-in hooks ship in the repo's `hooks/` directory (discovered like built-in skills via `BUILTIN_HOOKS_DIR`). User hooks override built-in hooks with the same name.

### hook.py Convention

Define functions named `on_<event>`:

```python
def on_pre_tool_use(context):
    """Block delete operations on important bodies."""
    if context["tool_name"] == "execute_code":
        code = context["arguments"].get("code", "")
        if "removeObject" in code:
            return {"block": True, "reason": "Blocked: removeObject is dangerous"}
    return {}

def on_post_tool_use(context):
    """Log every tool call."""
    with open("/tmp/tool_log.txt", "a") as f:
        f.write(f"{context['tool_name']}: {context['success']}\n")
```

A hook module can handle any combination of events — just define the corresponding `on_*` functions. Functions not defined are simply not called for that event.

## Events (v1)

### `pre_tool_use`

Fires before a tool call executes.

**Context:**

| Key | Type | Description |
|-----|------|-------------|
| `tool_name` | str | Name of the tool being called |
| `arguments` | dict | Tool call arguments |
| `turn` | int | Current turn number in the agentic loop |

**Return values:**
- `{"block": True, "reason": "..."}` — block the tool call, return error to LLM
- `{}` or `None` — allow

**Thread:** Worker thread. Must NOT call FreeCAD GUI APIs.

### `post_tool_use`

Fires after a tool call completes.

**Context:**

| Key | Type | Description |
|-----|------|-------------|
| `tool_name` | str | Name of the tool that was called |
| `arguments` | dict | Tool call arguments |
| `success` | bool | Whether the tool call succeeded |
| `output` | str | Tool output text |
| `error` | str | Error message (empty if success) |
| `turn` | int | Current turn number |

**Return values:** Ignored (informational only).

**Thread:** Worker thread. Must NOT call FreeCAD GUI APIs.

### `user_prompt_submit`

Fires before a user message is sent to the LLM.

**Context:**

| Key | Type | Description |
|-----|------|-------------|
| `text` | str | User's message text |
| `images` | list | Attached images (list of dicts) |
| `mode` | str | "plan" or "act" |

**Return values:**
- `{"block": True, "reason": "..."}` — block the message, show reason to user
- `{"modify": "new text"}` — replace the message text
- `{}` or `None` — allow unchanged

**Thread:** Main thread. FreeCAD API access is safe.

### `post_response`

Fires after the LLM response is fully processed and stored.

**Context:**

| Key | Type | Description |
|-----|------|-------------|
| `response_text` | str | Full response text |
| `tool_calls_count` | int | Number of tool calls made |
| `mode` | str | "plan" or "act" |

**Return values:** Ignored (informational only).

**Thread:** Main thread. FreeCAD API access is safe.

## Hook Registry

### `freecad_ai/hooks/registry.py`

```python
class HookRegistry:
    """Discovers hook directories and loads hook.py modules."""

    def __init__(self):
        self._hooks = {}  # {event_name: [(hook_name, callable)]}
        self._errors = {}  # {hook_name: error_message}
        self._load_hooks()

    def _load_hooks(self):
        # Scan BUILTIN_HOOKS_DIR then HOOKS_DIR
        # For each directory with hook.py:
        #   Import module dynamically (importlib.util)
        #   Do NOT add to sys.modules (ensures clean reload)
        #   Find on_* attributes, check callable() before registering
        #   Register each under its event name
        #   Skip disabled hooks (from config.hooks_disabled)
        # If directory doesn't exist, silently skip (common on first run)

    def fire(self, event: str, context: dict) -> dict:
        # Call each registered handler in alphabetical order by hook name
        # For blocking events: if any returns block=True, return immediately
        # For modify: chain modifications — mutate context["text"] between hooks
        #   so each hook sees the previous hook's output
        # Catch exceptions per-hook (log to FreeCAD console, continue)
        # Return merged result
        merged = {}
        for hook_name, handler in self._hooks.get(event, []):
            if "modify" in merged:
                context["text"] = merged["modify"]
            try:
                result = handler(context)
            except Exception:
                logger.error(...)
                continue
            if result and isinstance(result, dict):
                if result.get("block"):
                    return result  # block wins immediately
                merged.update(result)
        return merged

    def reload(self):
        # Atomic dict replacement — safe for concurrent fire() on worker thread.
        # CPython's GIL makes reference assignment atomic; the worker thread
        # holds a reference to the old dict until it finishes iterating.
        new_hooks = {}
        new_errors = {}
        self._discover(new_hooks, new_errors)
        self._hooks = new_hooks    # atomic reference swap
        self._errors = new_errors

    @property
    def discovered_hooks(self) -> list[dict]:
        # Returns [{name, events, has_error, error_message}] for Settings UI
```

### `freecad_ai/hooks/__init__.py`

```python
_registry = None

def get_hook_registry():
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry

def fire_hook(event: str, context: dict) -> dict:
    return get_hook_registry().fire(event, context)
```

Lazy singleton — created on first `fire_hook()` call. To avoid a race between main and worker threads, the registry is initialized eagerly in `ChatDockWidget.__init__` by calling `get_hook_registry()`. This ensures creation happens on the main thread before any worker threads exist.

## Integration Points

### `user_prompt_submit` — in `ChatDockWidget._send_message()`

Before `conversation.add_user_message()`:

```python
from ..hooks import fire_hook
result = fire_hook("user_prompt_submit", {
    "text": text, "images": images, "mode": mode,
})
if result.get("block"):
    self._append_html(render_message("system",
        f"Blocked by hook: {result.get('reason', '')}"))
    return
if result.get("modify"):
    text = result["modify"]
```

### `pre_tool_use` — in `_LLMWorker._tool_loop()`

Before the tool execution block (before the `if tc.name == "optimize_iteration"` check):

```python
from ..hooks import fire_hook
hook_result = fire_hook("pre_tool_use", {
    "tool_name": tc.name, "arguments": tc.arguments, "turn": turn,
})
if hook_result.get("block"):
    result = {"success": False, "output": "",
              "error": f"Blocked by hook: {hook_result.get('reason', '')}"}
else:
    # existing tool execution code (optimize_iteration check, etc.)
```

When blocked, the tool result is an error — the LLM sees the block reason and can adjust.

### `post_tool_use` — in `_LLMWorker._tool_loop()`

After `tool_call_finished.emit()`:

```python
fire_hook("post_tool_use", {
    "tool_name": tc.name, "arguments": tc.arguments,
    "success": success, "output": output, "error": error, "turn": turn,
})
```

### `post_response` — in `ChatDockWidget._on_response_finished()`

After `_store_tool_results()` and `conversation.save()`:

```python
from ..hooks import fire_hook
fire_hook("post_response", {
    "response_text": full_response,
    "tool_calls_count": len(self._worker._tool_results) if self._worker else 0,
    "mode": "plan" if self.mode_combo.currentIndex() == 0 else "act",
})
```

## Threading

| Event | Thread | FreeCAD API safe? |
|-------|--------|-------------------|
| `pre_tool_use` | Worker | No |
| `post_tool_use` | Worker | No |
| `user_prompt_submit` | Main | Yes |
| `post_response` | Main | Yes |

Worker-thread hooks must not call `App.ActiveDocument`, `FreeCADGui`, or any Qt widget methods. They can read/write files, make HTTP requests, or log. This must be documented clearly in the hook API.

## Exception Handling

A broken hook must never crash FreeCAD. Every handler call is wrapped:

```python
try:
    result = handler(context)
except Exception as e:
    logger.error("Hook '%s' raised %s in %s: %s", hook_name, type(e).__name__, event, e)
    # Continue to next hook
```

Errors are also tracked in `self._errors` so the Settings UI can show which hooks failed.

## Config Changes

New constant in `config.py`:

```python
HOOKS_DIR = os.path.join(CONFIG_DIR, "hooks")
```

Added to `_ensure_dirs()` so the directory is created on first launch.

New field in `AppConfig`:

```python
hooks_disabled: list = field(default_factory=list)
# List of hook directory names to skip (e.g., ["my-broken-hook"])
```

No other config needed — hook presence is sufficient for discovery.

## Settings UI

A "Hooks" group in the settings dialog:

- **List** — shows discovered hooks with status indicators:
  - Checkmark: loaded successfully, shows which events it handles
  - Cross (red): load error, shows error message
  - Unchecked: disabled
- **Add** — file picker to copy a `hook.py` into a new named hook directory (prompts for directory name)
- **Edit** — opens `hook.py` in the system's default text editor (`QDesktopServices.openUrl`)
- **Remove** — deletes the hook directory (with confirmation dialog). Built-in hooks (from repo's `hooks/` directory) cannot be removed, only disabled.
- **Reload** — calls `registry.reload()` to re-scan without restarting FreeCAD

Checking/unchecking a hook toggles it in `hooks_disabled`.

## Built-in Hook

One built-in hook ships with the workbench at `hooks/log-tool-calls/hook.py`:

```python
"""Log all tool calls to the FreeCAD report view."""
import logging
logger = logging.getLogger("freecad_ai.hooks.log_tool_calls")

def on_post_tool_use(context):
    level = logging.INFO if context["success"] else logging.WARNING
    logger.log(level, "Tool: %s | success=%s | %s",
               context["tool_name"],
               context["success"],
               context.get("error", ""))
```

Serves as a working example and is useful for debugging.

## File Layout

### New Files

| File | Purpose |
|------|---------|
| `freecad_ai/hooks/__init__.py` | `fire_hook()`, `get_hook_registry()` singleton |
| `freecad_ai/hooks/registry.py` | `HookRegistry` — discovery, loading, firing |
| `hooks/log-tool-calls/hook.py` | Built-in logging hook |
| `tests/unit/test_hooks.py` | Tests for registry, firing, blocking, error handling |

### Modified Files

| File | Change |
|------|--------|
| `freecad_ai/config.py` | Add `HOOKS_DIR` constant, `hooks_disabled` field, add to `_ensure_dirs()` |
| `freecad_ai/ui/chat_widget.py` | Add `fire_hook()` calls at 4 integration points, eager `get_hook_registry()` in `__init__` |
| `freecad_ai/ui/settings_dialog.py` | Add Hooks group (list, add, edit, remove, reload) |

## Key Design Decisions

1. **Directory-based discovery** — consistent with skills and user tools. Each hook is independent, easy to share/copy.
2. **`on_<event>` naming** — no registration, no decorators, no config files. Just name your function and it works.
3. **Alphabetical ordering** — deterministic, predictable. If order matters, prefix with numbers (`01-safety/`, `02-logger/`).
4. **Block wins** — if any hook blocks, the action is blocked. No voting or priority system.
5. **Modify chains** — for `user_prompt_submit`, each hook sees the output of the previous one. Last hook wins on conflicts.
6. **Exception isolation** — broken hooks log errors, never crash. Users can see errors in Settings UI.
7. **Lazy singleton** — no startup cost if no hooks are defined.
8. **Thread documentation** — clear about which events are safe for FreeCAD API access.
