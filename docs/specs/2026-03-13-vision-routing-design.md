# Vision Routing — Design Spec

**Date**: 2026-03-13
**Status**: Approved

## Overview

Route image handling based on LLM vision capability. Vision-capable models receive images inline as content blocks (existing behavior). Non-vision models get images auto-described via an MCP `describe_image` tool, with the text description substituted into the message. When no vision path exists at all (no native vision, no MCP fallback), image UI controls are disabled.

## Vision Detection

### Probe via Test Connection

When the user clicks "Test Connection" in the settings dialog and the connection test succeeds, a second request is sent:

1. Send a tiny 8x8 solid red PNG (~100 bytes) with the prompt: "What color is this image? Reply with only the color name."
2. Check if the response contains "red" (case-insensitive).
3. Set `vision_detected = True` or `False` accordingly.
4. Show result in test output: "Vision: supported" (green) or "Vision: not supported" (gray).

If the connection test itself fails, the vision probe is skipped and `vision_detected` is unchanged.

The probe runs **only** on explicit "Test Connection" clicks — never automatically on first message.

### MCP Fallback Discovery

After the probe, if `vision_detected == False`:

1. Search registered MCP tools for one with `describe_image` in the tool name (substring match).
2. If found, store its full registry name (e.g. `"llm-vision-mcp__describe_image"`) in `vision_fallback_tool`.
3. If not found, set `vision_fallback_tool = None`.

Since MCP servers connect lazily (on first message, not at startup), the fallback search also runs when MCP servers connect if `vision_fallback_tool` is still `None` and `supports_vision` is `False`.

## Config Changes

### New fields in `AppConfig`

```python
vision_detected: bool | None = None     # None=not tested, True/False=probe result
vision_override: bool | None = None     # user manual override, takes precedence
vision_fallback_tool: str | None = None # e.g. "llm-vision-mcp__describe_image"
```

### Derived property

```python
@property
def supports_vision(self) -> bool:
    if self.vision_override is not None:
        return self.vision_override
    if self.vision_detected is not None:
        return self.vision_detected
    return False  # unknown = assume no
```

### Reset logic

- **Provider or model changes**: `vision_detected` resets to `None`, `vision_fallback_tool` resets to `None`. `vision_override` is preserved (user's explicit choice persists across model changes).
- **MCP server config changes** (add/remove): `vision_fallback_tool` resets to `None` (re-searched on next connect).

## Image Interception

### In the LLM worker, before sending messages

When `config.supports_vision == False` and the outgoing message contains image content blocks:

1. For each image block, call the MCP fallback tool via `registry.execute(vision_fallback_tool, {"image": "<base64_data>", "prompt": "Describe this image in detail."})`.
2. Replace the image block with a text block: `[Image described by llm-vision-mcp: <description>]`.
3. Emit a signal so the chat UI shows a subtle note: "Image auto-described by llm-vision-mcp".
4. Send the modified (text-only) message to the LLM.

### Behavior by scenario

| `supports_vision` | MCP fallback | Behavior | UI |
|---|---|---|---|
| `True` | any | Images sent inline as base64 content blocks | All image controls enabled |
| `False` | found | Images auto-described via MCP, sent as text | All image controls enabled, note shown in chat |
| `False` | `None` | Images dropped with warning in chat | Capture, Attach, drag-drop, paste disabled |
| untested (`None`) | unknown | Assume no vision; image controls enabled (optimistic) | Hint on first image use: "Tip: click Test Connection in Settings to enable vision auto-detection." |

## UI Changes

### Settings Dialog — Behavior section

New row: **"Model supports vision"**

- Checkbox with a label showing detection state:
  - `☐ Model supports vision (not tested)` — `vision_detected` is `None`, no override
  - `☑ Model supports vision (auto-detected)` — probe returned `True`
  - `☐ Model supports vision (auto-detected)` — probe returned `False`
  - `☑ Model supports vision (manual override)` / `☐ ... (manual override)` — user toggled
- A "Reset" button appears when `vision_override is not None`, clears it back to auto-detected value.

### Chat Widget — image control gating

When `supports_vision == False` AND `vision_fallback_tool is None`:

- **Capture button**: disabled, tooltip "No vision support — configure a vision MCP server or enable in Settings"
- **Attach button**: disabled, same tooltip
- **Drag-drop**: disabled (ignore drop events for images)
- **Paste-image**: disabled (ignore image mime data)

When `supports_vision == False` AND `vision_fallback_tool` exists:

- All image controls enabled — images will be auto-described via MCP.

When `supports_vision == True`:

- All image controls enabled — current behavior, images sent inline.

### Refresh timing

Image control state refreshes:

- After settings are saved
- After MCP servers connect (fallback tool may become available)

## Files to Modify

| File | Change |
|---|---|
| `freecad_ai/config.py` | Add `vision_detected`, `vision_override`, `vision_fallback_tool` fields, `supports_vision` property, reset logic |
| `freecad_ai/ui/settings_dialog.py` | Add vision checkbox + reset button to Behavior section, vision probe in test connection flow |
| `freecad_ai/ui/chat_widget.py` | Gate Capture/Attach/drag-drop/paste on vision state, show substitution notes, show hint for untested state |
| `freecad_ai/llm/client.py` | Vision probe method (send test image, check response) |
| `freecad_ai/mcp/manager.py` | Fallback tool search method |
| `freecad_ai/core/conversation.py` or `chat_widget.py` worker | Image interception and MCP describe_image dispatch |
| `tests/unit/test_vision_routing.py` | Unit tests for config logic, probe parsing, interception, UI gating |
