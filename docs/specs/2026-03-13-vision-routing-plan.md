# Vision Routing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route images based on LLM vision capability — inline for vision models, auto-described via MCP for non-vision models, disabled when no vision path exists.

**Architecture:** Add `vision_detected`/`vision_override` config fields with a `supports_vision` property. Probe vision on Test Connection via a random-number image. Intercept images in `Conversation.get_messages_for_api()` using a `describe_fn` callback. Gate UI controls (Capture, Attach, drag-drop, paste) based on vision state.

**Tech Stack:** Python 3.11, PySide2, QPainter (probe image generation), existing MCP/tool registry infrastructure.

---

## Chunk 1: Config & Vision Probe

### Task 1: Config fields and supports_vision property

**Files:**
- Modify: `freecad_ai/config.py:61-88`
- Test: `tests/unit/test_vision_routing.py` (create)

- [ ] **Step 1: Write failing tests for config fields**

```python
# tests/unit/test_vision_routing.py
"""Tests for vision routing."""

from freecad_ai.config import AppConfig


class TestVisionConfig:
    """Config fields and supports_vision property."""

    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.vision_detected is None
        assert cfg.vision_override is None

    def test_supports_vision_override_takes_precedence(self):
        cfg = AppConfig()
        cfg.vision_detected = False
        cfg.vision_override = True
        assert cfg.supports_vision is True

    def test_supports_vision_detected_used_when_no_override(self):
        cfg = AppConfig()
        cfg.vision_detected = True
        assert cfg.supports_vision is True

    def test_supports_vision_false_when_detected_false(self):
        cfg = AppConfig()
        cfg.vision_detected = False
        assert cfg.supports_vision is False

    def test_supports_vision_false_when_untested(self):
        cfg = AppConfig()
        assert cfg.supports_vision is False

    def test_vision_fields_roundtrip_json(self):
        cfg = AppConfig()
        cfg.vision_detected = True
        cfg.vision_override = False
        d = cfg.to_dict()
        cfg2 = AppConfig.from_dict(d)
        assert cfg2.vision_detected is True
        assert cfg2.vision_override is False

    def test_vision_fields_none_roundtrip(self):
        cfg = AppConfig()
        d = cfg.to_dict()
        cfg2 = AppConfig.from_dict(d)
        assert cfg2.vision_detected is None
        assert cfg2.vision_override is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py -v`
Expected: FAIL — `AppConfig` has no `vision_detected` / `supports_vision`

- [ ] **Step 3: Add config fields and property**

In `freecad_ai/config.py`, add to `AppConfig` after line 76 (`scan_freecad_macros`):

```python
    vision_detected: bool | None = None   # None=not tested, True/False=probe result
    vision_override: bool | None = None   # user manual override, takes precedence

    @property
    def supports_vision(self) -> bool:
        """Whether the current LLM supports vision (images in content blocks)."""
        if self.vision_override is not None:
            return self.vision_override
        if self.vision_detected is not None:
            return self.vision_detected
        return False
```

Note: `vision_detected` and `vision_override` use `bool | None` which `asdict()` serializes as JSON `null`. The existing `from_dict()` with its `known` field filter will handle this correctly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/config.py tests/unit/test_vision_routing.py
git commit -m "feat: add vision_detected and vision_override config fields"
```

---

### Task 2: Vision probe image generation

**Files:**
- Modify: `freecad_ai/llm/client.py:103-106`
- Test: `tests/unit/test_vision_routing.py`

- [ ] **Step 1: Write failing tests for probe image and response checking**

Append to `tests/unit/test_vision_routing.py`:

```python
import re


class TestVisionProbe:
    """Vision probe image generation and response parsing."""

    def test_generate_probe_image_returns_png_bytes(self):
        from freecad_ai.llm.client import _generate_probe_image
        number, png_bytes = _generate_probe_image()
        assert 100 <= number <= 999
        assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'  # PNG magic bytes
        assert len(png_bytes) > 50  # non-trivial content

    def test_generate_probe_image_random(self):
        from freecad_ai.llm.client import _generate_probe_image
        numbers = {_generate_probe_image()[0] for _ in range(20)}
        assert len(numbers) > 1  # not always the same number

    def test_check_probe_response_exact_match(self):
        from freecad_ai.llm.client import _check_probe_response
        assert _check_probe_response("427", 427) is True

    def test_check_probe_response_in_sentence(self):
        from freecad_ai.llm.client import _check_probe_response
        assert _check_probe_response("The number shown is 427.", 427) is True

    def test_check_probe_response_wrong_number(self):
        from freecad_ai.llm.client import _check_probe_response
        assert _check_probe_response("The number is 123.", 427) is False

    def test_check_probe_response_no_number(self):
        from freecad_ai.llm.client import _check_probe_response
        assert _check_probe_response("I cannot see any image.", 427) is False

    def test_check_probe_response_empty(self):
        from freecad_ai.llm.client import _check_probe_response
        assert _check_probe_response("", 427) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestVisionProbe -v`
Expected: FAIL — `_generate_probe_image` not found

- [ ] **Step 3: Implement probe image generation and response checking**

In `freecad_ai/llm/client.py`, add these module-level functions before the `LLMClient` class:

```python
import base64
import random


def _generate_probe_image() -> tuple[int, bytes]:
    """Generate a small PNG with a random 3-digit number for vision probing.

    Returns (number, png_bytes).
    Uses QPainter if available, falls back to a minimal manual PNG.
    """
    number = random.randint(100, 999)
    try:
        from PySide2.QtGui import QImage, QPainter, QFont, QColor
        from PySide2.QtCore import Qt
        import io

        img = QImage(64, 32, QImage.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        painter = QPainter(img)
        painter.setPen(QColor(0, 0, 0))
        font = QFont("Sans", 16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(img.rect(), Qt.AlignCenter, str(number))
        painter.end()

        buf = QtCore.QBuffer()
        buf.open(QtCore.QBuffer.WriteOnly)
        img.save(buf, "PNG")
        png_bytes = bytes(buf.data())
        buf.close()
        return number, png_bytes
    except ImportError:
        # Fallback: create minimal 1x1 white PNG (for unit tests without Qt)
        # The number won't be visible but the function signature is correct
        import struct
        import zlib

        def _minimal_png() -> bytes:
            """Create a minimal valid 1x1 white PNG."""
            signature = b'\x89PNG\r\n\x1a\n'
            # IHDR
            ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF
            ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
            # IDAT
            raw = zlib.compress(b'\x00\xff\xff\xff')
            idat_crc = zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF
            idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
            # IEND
            iend_crc = zlib.crc32(b'IEND') & 0xFFFFFFFF
            iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
            return signature + ihdr + idat + iend

        return number, _minimal_png()


def _check_probe_response(response: str, expected_number: int) -> bool:
    """Check if the LLM response contains the expected number."""
    return str(expected_number) in response
```

Also add the missing import at the top of the file (after existing imports):
```python
from PySide2 import QtCore  # needed for QBuffer in probe image
```

Wait — this import will fail in unit tests. The `QtCore` import should be inside the try block in `_generate_probe_image`. Update the QPainter path to use:

```python
        from PySide2 import QtCore as _QtCore
        buf = _QtCore.QBuffer()
        buf.open(_QtCore.QBuffer.WriteOnly)
```

No top-level PySide2 import needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestVisionProbe -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/llm/client.py tests/unit/test_vision_routing.py
git commit -m "feat: add vision probe image generation and response checking"
```

---

### Task 3: vision_probe() method on LLMClient

**Files:**
- Modify: `freecad_ai/llm/client.py` (add method after `test_connection` at line 106)
- Test: `tests/unit/test_vision_routing.py`

- [ ] **Step 1: Write failing test for vision_probe**

Append to `tests/unit/test_vision_routing.py`:

```python
from unittest.mock import patch, MagicMock


class TestVisionProbeMethod:
    """LLMClient.vision_probe() integration."""

    @patch("freecad_ai.llm.client._generate_probe_image")
    def test_vision_probe_returns_true_for_correct_answer(self, mock_gen):
        from freecad_ai.llm.client import LLMClient
        mock_gen.return_value = (427, b'\x89PNG\r\n\x1a\nfakedata')
        client = LLMClient("openai", "http://localhost", "", "test-model")
        with patch.object(client, "send", return_value="427"):
            assert client.vision_probe() is True

    @patch("freecad_ai.llm.client._generate_probe_image")
    def test_vision_probe_returns_false_for_wrong_answer(self, mock_gen):
        from freecad_ai.llm.client import LLMClient
        mock_gen.return_value = (427, b'\x89PNG\r\n\x1a\nfakedata')
        client = LLMClient("openai", "http://localhost", "", "test-model")
        with patch.object(client, "send", return_value="I cannot see images"):
            assert client.vision_probe() is False

    @patch("freecad_ai.llm.client._generate_probe_image")
    def test_vision_probe_returns_false_on_error(self, mock_gen):
        from freecad_ai.llm.client import LLMClient
        mock_gen.return_value = (427, b'\x89PNG\r\n\x1a\nfakedata')
        client = LLMClient("openai", "http://localhost", "", "test-model")
        with patch.object(client, "send", side_effect=Exception("API error")):
            assert client.vision_probe() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestVisionProbeMethod -v`
Expected: FAIL — `LLMClient` has no `vision_probe`

- [ ] **Step 3: Implement vision_probe()**

Add to `LLMClient` after `test_connection()` (after line 106 in `client.py`):

```python
    def vision_probe(self) -> bool:
        """Test if the model supports vision by sending an image with a number.

        Returns True if the model correctly identifies the number, False otherwise.
        """
        try:
            number, png_bytes = _generate_probe_image()
            b64 = base64.b64encode(png_bytes).decode("ascii")

            if self.api_style == "anthropic":
                messages = [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "What number is shown in this image? Reply with only the number.",
                        },
                    ],
                }]
            else:
                # OpenAI-compatible format
                data_uri = f"data:image/png;base64,{b64}"
                messages = [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        },
                        {
                            "type": "text",
                            "text": "What number is shown in this image? Reply with only the number.",
                        },
                    ],
                }]

            response = self.send(messages, system="Respond briefly.")
            return _check_probe_response(response, number)
        except Exception:
            return False
```

Also add `import base64` at the top of `client.py` if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestVisionProbeMethod -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add freecad_ai/llm/client.py tests/unit/test_vision_routing.py
git commit -m "feat: add vision_probe() method to LLMClient"
```

---

## Chunk 2: MCP Fallback Discovery & Image Interception

### Task 4: MCP fallback tool search

**Files:**
- Modify: `freecad_ai/mcp/manager.py:114-127`
- Test: `tests/unit/test_vision_routing.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_vision_routing.py`:

```python
class TestFallbackDiscovery:
    """MCP fallback tool search."""

    def test_find_vision_fallback_found(self):
        from freecad_ai.tools.registry import ToolRegistry, ToolDefinition, ToolResult
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="llm-vision-mcp__describe_image",
            description="Describe an image",
            parameters=[],
            handler=lambda **kw: ToolResult(success=True, output="test"),
            category="mcp",
        ))
        from freecad_ai.mcp.manager import find_vision_fallback
        assert find_vision_fallback(registry) == "llm-vision-mcp__describe_image"

    def test_find_vision_fallback_not_found(self):
        from freecad_ai.tools.registry import ToolRegistry
        registry = ToolRegistry()
        from freecad_ai.mcp.manager import find_vision_fallback
        assert find_vision_fallback(registry) is None

    def test_find_vision_fallback_partial_name_match(self):
        from freecad_ai.tools.registry import ToolRegistry, ToolDefinition, ToolResult
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="my_server__describe_image",
            description="Vision tool",
            parameters=[],
            handler=lambda **kw: ToolResult(success=True, output="test"),
            category="mcp",
        ))
        from freecad_ai.mcp.manager import find_vision_fallback
        assert find_vision_fallback(registry) == "my_server__describe_image"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestFallbackDiscovery -v`
Expected: FAIL — `find_vision_fallback` not found

- [ ] **Step 3: Implement find_vision_fallback**

Add to `freecad_ai/mcp/manager.py` as a module-level function (after the `MCPManager` class):

```python
def find_vision_fallback(registry) -> str | None:
    """Search the tool registry for a describe_image tool (MCP vision fallback).

    Returns the full tool name if found, None otherwise.
    """
    for tool in registry.list_tools():
        if "describe_image" in tool.name:
            return tool.name
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestFallbackDiscovery -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add freecad_ai/mcp/manager.py tests/unit/test_vision_routing.py
git commit -m "feat: add find_vision_fallback() for MCP describe_image discovery"
```

---

### Task 5: Image interception in Conversation

**Files:**
- Modify: `freecad_ai/core/conversation.py:77-135`
- Test: `tests/unit/test_vision_routing.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_vision_routing.py`:

```python
class TestImageInterception:
    """Image block replacement in get_messages_for_api."""

    def _make_conversation_with_image(self):
        from freecad_ai.core.conversation import Conversation
        conv = Conversation()
        conv.add_user_message("Look at this", images=[
            {"type": "image", "source": "base64", "media_type": "image/png", "data": "abc123"},
        ])
        return conv

    def test_no_describe_fn_keeps_images(self):
        conv = self._make_conversation_with_image()
        msgs = conv.get_messages_for_api(api_style="openai")
        # Should still have image_url block
        content = msgs[0]["content"]
        types = [b["type"] for b in content]
        assert "image_url" in types

    def test_describe_fn_replaces_images(self):
        conv = self._make_conversation_with_image()

        def mock_describe(b64_data):
            return f"Description of image ({len(b64_data)} bytes)"

        msgs = conv.get_messages_for_api(api_style="openai", describe_fn=mock_describe)
        content = msgs[0]["content"]
        types = [b["type"] for b in content]
        assert "image_url" not in types
        assert "text" in types
        # Find the description block
        desc_blocks = [b for b in content if "Description of image" in b.get("text", "")]
        assert len(desc_blocks) == 1
        assert "(6 bytes)" in desc_blocks[0]["text"]  # len("abc123") == 6

    def test_describe_fn_error_produces_error_text(self):
        conv = self._make_conversation_with_image()

        def failing_describe(b64_data):
            raise RuntimeError("MCP server crashed")

        msgs = conv.get_messages_for_api(api_style="openai", describe_fn=failing_describe)
        content = msgs[0]["content"]
        types = [b["type"] for b in content]
        assert "image_url" not in types
        desc_blocks = [b for b in content if "description unavailable" in b.get("text", "")]
        assert len(desc_blocks) == 1
        assert "MCP server crashed" in desc_blocks[0]["text"]

    def test_describe_fn_with_anthropic_format(self):
        conv = self._make_conversation_with_image()

        def mock_describe(b64_data):
            return "A red square"

        msgs = conv.get_messages_for_api(api_style="anthropic", describe_fn=mock_describe)
        content = msgs[0]["content"]
        types = [b["type"] for b in content]
        assert "image" not in types
        desc_blocks = [b for b in content if "A red square" in b.get("text", "")]
        assert len(desc_blocks) == 1

    def test_multiple_images_all_replaced(self):
        from freecad_ai.core.conversation import Conversation
        conv = Conversation()
        conv.add_user_message("Two images", images=[
            {"type": "image", "source": "base64", "media_type": "image/png", "data": "img1"},
            {"type": "image", "source": "base64", "media_type": "image/png", "data": "img2"},
        ])
        descriptions = []

        def mock_describe(b64_data):
            desc = f"Described {b64_data}"
            descriptions.append(desc)
            return desc

        msgs = conv.get_messages_for_api(api_style="openai", describe_fn=mock_describe)
        content = msgs[0]["content"]
        assert len(descriptions) == 2
        image_blocks = [b for b in content if b.get("type") == "image_url"]
        assert len(image_blocks) == 0

    def test_partial_failure_continues(self):
        from freecad_ai.core.conversation import Conversation
        conv = Conversation()
        conv.add_user_message("Two images", images=[
            {"type": "image", "source": "base64", "media_type": "image/png", "data": "img1"},
            {"type": "image", "source": "base64", "media_type": "image/png", "data": "img2"},
        ])
        call_count = [0]

        def flaky_describe(b64_data):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Server timeout")
            return "Second image described"

        msgs = conv.get_messages_for_api(api_style="openai", describe_fn=flaky_describe)
        content = msgs[0]["content"]
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]
        full_text = " ".join(texts)
        assert "description unavailable" in full_text
        assert "Second image described" in full_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestImageInterception -v`
Expected: FAIL — `get_messages_for_api` doesn't accept `describe_fn`

- [ ] **Step 3: Implement image interception**

Modify `Conversation.get_messages_for_api()` in `freecad_ai/core/conversation.py`:

Change the method signature at line 77:
```python
    def get_messages_for_api(self, max_chars: int = 100000,
                             api_style: str = "openai",
                             describe_fn=None) -> list[dict]:
```

Add a new step before the format conversion block (before line 131 `# Convert to provider format`):

```python
        # Replace image blocks with text descriptions if describe_fn is provided
        if describe_fn:
            result = self._replace_images_with_descriptions(result, describe_fn)
```

Add the helper method to the `Conversation` class:

```python
    @staticmethod
    def _replace_images_with_descriptions(messages: list[dict],
                                          describe_fn) -> list[dict]:
        """Replace image content blocks with text descriptions from describe_fn.

        Images are processed serially. On failure, an error text block is
        substituted so remaining images can still be processed.
        """
        result = []
        for msg in messages:
            if not isinstance(msg.get("content"), list):
                result.append(msg)
                continue
            new_blocks = []
            for block in msg["content"]:
                if block.get("type") == "image":
                    b64_data = block.get("data", "")
                    try:
                        description = describe_fn(b64_data)
                        new_blocks.append({
                            "type": "text",
                            "text": f"[Image described by llm-vision-mcp: {description}]",
                        })
                    except Exception as e:
                        new_blocks.append({
                            "type": "text",
                            "text": f"[Image: description unavailable — MCP error: {e}]",
                        })
                else:
                    new_blocks.append(block)
            result.append({**msg, "content": new_blocks})
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py::TestImageInterception -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests pass (the new `describe_fn=None` default is backward-compatible)

- [ ] **Step 6: Commit**

```bash
git add freecad_ai/core/conversation.py tests/unit/test_vision_routing.py
git commit -m "feat: add image interception with describe_fn in get_messages_for_api"
```

---

## Chunk 3: Settings Dialog & Test Connection Integration

### Task 6: Vision checkbox in settings dialog

**Files:**
- Modify: `freecad_ai/ui/settings_dialog.py:120-180` (Behavior section), `:266-302` (load), `:313-344` (save)

- [ ] **Step 1: Add vision checkbox and reset button to Behavior section**

In `settings_dialog.py`, after the resolution layout block (after line 177, before `behavior_group.setLayout`):

```python
        # Vision support
        vision_layout = QHBoxLayout()
        self.vision_check = QCheckBox(
            translate("SettingsDialog", "Model supports vision")
        )
        self.vision_check.setToolTip(
            translate("SettingsDialog",
                      "When enabled, images are sent directly to the LLM.\n"
                      "When disabled, images are described via MCP before sending.\n"
                      "Use Test Connection to auto-detect.")
        )
        self.vision_check.stateChanged.connect(self._on_vision_override_changed)
        vision_layout.addWidget(self.vision_check)

        self._vision_status_label = QLabel()
        self._vision_status_label.setStyleSheet("color: #888;")
        vision_layout.addWidget(self._vision_status_label)

        self._vision_reset_btn = QPushButton(translate("SettingsDialog", "Reset"))
        self._vision_reset_btn.setMaximumWidth(50)
        self._vision_reset_btn.setToolTip(
            translate("SettingsDialog", "Clear manual override, use auto-detected value")
        )
        self._vision_reset_btn.clicked.connect(self._reset_vision_override)
        self._vision_reset_btn.hide()
        vision_layout.addWidget(self._vision_reset_btn)

        vision_layout.addStretch()
        behavior_layout.addLayout(vision_layout)
```

- [ ] **Step 2: Add load/save logic and helper methods**

In `_load_from_config()`, after the resolution map block (after line 291):

```python
        # Vision
        self._update_vision_ui(cfg)
```

In `_save()`, after resolution_values block (after line 338):

```python
        # Vision override
        if hasattr(self, '_vision_override_value'):
            cfg.vision_override = self._vision_override_value
        # Reset vision_detected if provider or model changed
        old_provider = getattr(self, '_original_provider', None)
        old_model = getattr(self, '_original_model', None)
        if (old_provider and cfg.provider.name != old_provider) or \
           (old_model and cfg.provider.model != old_model):
            cfg.vision_detected = None
```

In `_load_from_config()`, store the original provider/model for reset detection:

```python
        self._original_provider = cfg.provider.name
        self._original_model = cfg.provider.model
```

Add helper methods to `SettingsDialog`:

```python
    def _update_vision_ui(self, cfg):
        """Update vision checkbox and label from config state."""
        self._vision_override_value = cfg.vision_override
        if cfg.vision_override is not None:
            self.vision_check.setChecked(cfg.vision_override)
            self._vision_status_label.setText(
                translate("SettingsDialog", "(manual override)")
            )
            self._vision_reset_btn.show()
        elif cfg.vision_detected is not None:
            self.vision_check.setChecked(cfg.vision_detected)
            self._vision_status_label.setText(
                translate("SettingsDialog", "(auto-detected)")
            )
            self._vision_reset_btn.hide()
        else:
            self.vision_check.setChecked(False)
            self._vision_status_label.setText(
                translate("SettingsDialog", "(not tested)")
            )
            self._vision_reset_btn.hide()

    def _on_vision_override_changed(self, state):
        """User toggled the vision checkbox — set manual override.

        PySide2 QCheckBox.stateChanged emits int (0=Unchecked, 2=Checked).
        """
        self._vision_override_value = (state != 0)
        self._vision_status_label.setText(
            translate("SettingsDialog", "(manual override)")
        )
        self._vision_reset_btn.show()

    def _reset_vision_override(self):
        """Clear the manual override, revert to auto-detected value."""
        cfg = get_config()
        self._vision_override_value = None
        self._update_vision_ui(cfg)
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add freecad_ai/ui/settings_dialog.py
git commit -m "feat: add vision support checkbox to settings dialog"
```

---

### Task 7: Vision probe in Test Connection flow

**Files:**
- Modify: `freecad_ai/ui/settings_dialog.py:41-55` (`_TestConnectionThread`), `:358-366` (`_on_test_finished`)

- [ ] **Step 1: Extend _TestConnectionThread to run vision probe**

Replace the `_TestConnectionThread` class:

```python
class _TestConnectionThread(QThread):
    """Background thread for testing LLM connection and vision capability."""
    finished = Signal(bool, str)        # success, message
    vision_result = Signal(bool)        # vision probe result

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            from ..llm.client import create_client_from_config
            client = create_client_from_config()
            response = client.test_connection()
            self.finished.emit(True, translate("SettingsDialog", "Connected! Response: ") + response)

            # Run vision probe after successful connection
            vision_ok = client.vision_probe()
            self.vision_result.emit(vision_ok)
        except Exception as e:
            self.finished.emit(False, str(e))
```

- [ ] **Step 2: Connect vision_result signal and update handler**

In `_test_connection()`, add signal connection after the existing `finished.connect`:

```python
        self._test_thread.vision_result.connect(self._on_vision_probed)
```

Add handler method (ensure `save_current_config` is imported from `freecad_ai.config`):

```python
    def _on_vision_probed(self, supports_vision: bool):
        """Handle vision probe result — persists to config immediately."""
        cfg = get_config()
        cfg.vision_detected = supports_vision
        save_current_config()
        self._update_vision_ui(cfg)
        # Append vision status to test output
        if supports_vision:
            current = self.test_status.text()
            self.test_status.setText(current + " | Vision: supported")
        else:
            current = self.test_status.text()
            self.test_status.setText(current + " | Vision: not supported")
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add freecad_ai/ui/settings_dialog.py
git commit -m "feat: add vision probe to Test Connection flow"
```

---

## Chunk 4: Chat Widget Integration

### Task 8: Wire describe_fn into message sending

**Files:**
- Modify: `freecad_ai/ui/chat_widget.py:43-60` (signals), `:77-101` (worker run), `:860-895` (message sending)

The key challenge: image description via MCP can be slow (seconds per image). Running it on the main thread would freeze the UI. The solution: pass `describe_fn` to the `_LLMWorker`, which runs on a background QThread. The worker calls `get_messages_for_api(describe_fn=...)` from the worker thread.

Currently, `get_messages_for_api()` is called on the main thread at line 881 and the result passed to the worker as `messages`. We need to restructure: pass the `Conversation` object (or a snapshot) to the worker and let it call `get_messages_for_api()` itself.

- [ ] **Step 1: Add vision_note signal to _LLMWorker**

In `_LLMWorker` class, after the existing signals (after line 59):

```python
    vision_note = Signal(str)              # Vision description status note
```

- [ ] **Step 2: Add describe_fn to _LLMWorker and move get_messages_for_api into worker**

Change `_LLMWorker.__init__` to accept `conversation`, `describe_fn`, and `max_chars`:

```python
    def __init__(self, messages, system_prompt, tools=None, registry=None,
                 api_style="openai", conversation=None, describe_fn=None,
                 parent=None):
        super().__init__(parent)
        self.messages = list(messages)
        self.system_prompt = system_prompt
        self.tools = tools
        self.registry = registry
        self.api_style = api_style
        self.conversation = conversation
        self.describe_fn = describe_fn
        # ... rest unchanged
```

In `_LLMWorker.run()`, re-fetch messages with `describe_fn` if both `conversation` and `describe_fn` are provided:

```python
    def run(self):
        try:
            from ..llm.client import create_client_from_config
            client = create_client_from_config()

            # Re-format messages with image interception on worker thread
            if self.conversation and self.describe_fn:
                wrapped = self._wrap_describe_fn(self.describe_fn)
                self.messages = self.conversation.get_messages_for_api(
                    api_style=self.api_style, describe_fn=wrapped
                )

            if not self.tools:
                self._simple_stream(client)
                return
            self._tool_loop(client)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _wrap_describe_fn(self, describe_fn):
        """Wrap describe_fn to emit vision_note signals."""
        def wrapped(b64_data):
            try:
                result = describe_fn(b64_data)
                self.vision_note.emit("Image auto-described by llm-vision-mcp")
                return result
            except Exception as e:
                self.vision_note.emit(f"Image description failed: {e}")
                raise
        return wrapped
```

- [ ] **Step 3: Build describe_fn on the main thread, pass to worker**

At line 881, where `get_messages_for_api` is currently called:

```python
        # Build describe_fn for non-vision LLMs
        describe_fn = None
        conversation_ref = None
        cfg = get_config()
        if not cfg.supports_vision:
            fallback = getattr(cfg, '_vision_fallback_tool', None)
            if fallback and self._tool_registry:
                _reg = self._tool_registry
                _tool = fallback
                def describe_fn(b64_data):
                    result = _reg.execute(
                        _tool, {"image": b64_data, "prompt": "Describe this image in detail."}
                    )
                    if result.success:
                        return result.output
                    raise RuntimeError(result.error or "describe_image failed")
                conversation_ref = self.conversation

        messages = self.conversation.get_messages_for_api(api_style=api_style)
```

Pass both to the worker constructor:

```python
        self._worker = _LLMWorker(
            messages, system_prompt, tools=tools_schema,
            registry=self._tool_registry, api_style=api_style,
            conversation=conversation_ref, describe_fn=describe_fn,
        )
```

When `conversation_ref` is not None, the worker will re-call `get_messages_for_api()` with the `describe_fn` on the worker thread, replacing the pre-fetched `messages`. When `conversation_ref` is None (vision is supported), the worker uses the pre-fetched messages as before.

Note: `registry.execute()` for MCP tools calls `MCPClient.call_tool()` which uses subprocess stdio — this is safe from any thread since it's blocking I/O on pipes.

- [ ] **Step 4: Connect vision_note signal**

After worker creation, connect the signal:

```python
        self._worker.vision_note.connect(self._on_vision_note)
```

Add handler:

```python
    def _on_vision_note(self, message: str):
        """Show a subtle note when images are auto-described."""
        self._append_html(
            f'<div style="color: #888; font-size: 9pt; margin: 2px 12px;">'
            f'{message}</div>'
        )
```

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add freecad_ai/ui/chat_widget.py
git commit -m "feat: wire describe_fn into LLM worker for non-vision image description"
```

---

### Task 9: Gate image UI controls

**Files:**
- Modify: `freecad_ai/ui/chat_widget.py:486-534` (button setup), `:289-360` (`_ImageAwareTextEdit`)

- [ ] **Step 1: Add method to refresh image control state**

Add to `ChatDockWidget`:

```python
    def _refresh_image_controls(self):
        """Enable/disable image controls based on vision capability."""
        cfg = get_config()
        fallback = getattr(cfg, '_vision_fallback_tool', None)

        # Disable only when we know there's no vision AND no fallback
        disable = (cfg.vision_detected is not None
                   and not cfg.supports_vision
                   and fallback is None)

        no_vision_tip = translate(
            "ChatDockWidget",
            "No vision support — configure a vision MCP server or enable in Settings"
        )

        self._capture_btn.setEnabled(not disable)
        self._attach_btn.setEnabled(not disable)
        self.input_edit.set_images_enabled(not disable)

        if disable:
            self._capture_btn.setToolTip(no_vision_tip)
            self._attach_btn.setToolTip(no_vision_tip)
```

- [ ] **Step 2: Add set_images_enabled to _ImageAwareTextEdit**

`_ImageAwareTextEdit` currently has no `__init__`. Add one and guard all image entry points:

```python
    def __init__(self, parent=None):
        super().__init__(parent)
        self._images_enabled = True

    def set_images_enabled(self, enabled: bool):
        """Enable or disable image paste and drag-drop."""
        self._images_enabled = enabled
        self.setAcceptDrops(enabled)
```

Guard **all** image entry methods — add at the top of each:

In `insertFromMimeData()`:
```python
        if not self._images_enabled:
            super().insertFromMimeData(source)
            return
```

In `_process_image_from_mime()`:
```python
        if not self._images_enabled:
            return
```

In `_process_image_file()`:
```python
        if not self._images_enabled:
            return
```

Note: `setAcceptDrops(False)` handles drag-drop, but paste via keyboard (Ctrl+V) goes through `insertFromMimeData`, which must also be guarded.

- [ ] **Step 3: Call _refresh_image_controls at the right times**

Add an instance variable to `ChatDockWidget.__init__`:

```python
        self._vision_fallback_tool = None  # runtime-only, found after MCP connect
```

Call `self._refresh_image_controls()` in three places:

1. **Widget init** — after buttons are created (initial state).

2. **`_open_settings()`** — after settings dialog closes. Clear fallback on provider/model or MCP config changes:

```python
        cfg = get_config()
        old_provider = cfg.provider.name
        old_model = cfg.provider.model
        old_mcp = list(cfg.mcp_servers)
        dlg = SettingsDialog(self)
        if dlg.exec_():
            cfg = get_config()
            if cfg.provider.name != old_provider or cfg.provider.model != old_model:
                self._vision_fallback_tool = None
            if cfg.mcp_servers != old_mcp:
                self._vision_fallback_tool = None  # re-searched on next MCP connect
            # If vision not supported and MCP already connected, search now
            if not cfg.supports_vision and self._vision_fallback_tool is None and self._tool_registry:
                from ..mcp.manager import find_vision_fallback
                self._vision_fallback_tool = find_vision_fallback(self._tool_registry)
            self._refresh_image_controls()
```

3. **`_connect_mcp_servers()`** — after MCP tools are registered, search for fallback:

```python
        from ..mcp.manager import find_vision_fallback
        cfg = get_config()
        if not cfg.supports_vision and self._vision_fallback_tool is None:
            self._vision_fallback_tool = find_vision_fallback(self._tool_registry)
        self._refresh_image_controls()
```

Update `_refresh_image_controls()` to use `self._vision_fallback_tool`:

```python
    def _refresh_image_controls(self):
        cfg = get_config()
        disable = (cfg.vision_detected is not None
                   and not cfg.supports_vision
                   and self._vision_fallback_tool is None)
        # ... rest as before
```

Similarly update Task 8's `describe_fn` construction to read `self._vision_fallback_tool` instead of config.

- [ ] **Step 4: Add vision hint for untested state**

Add instance variable in `__init__`:

```python
        self._vision_hint_shown = False
```

In `_send_message()`, before collecting images (around line 612):

```python
        # Show one-time hint if vision not tested and user is sending images
        images_present = self._attachment_strip.get_images()
        cfg = get_config()
        if images_present and cfg.vision_detected is None and not self._vision_hint_shown:
            self._vision_hint_shown = True
            self._append_html(
                '<div style="color: #888; font-size: 9pt; margin: 4px 12px;">'
                'Tip: click Test Connection in Settings to enable vision auto-detection.'
                '</div>'
            )
```

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add freecad_ai/ui/chat_widget.py
git commit -m "feat: gate image controls on vision capability"
```

---

### Task 10: Final integration test and cleanup

**Files:**
- Test: `tests/unit/test_vision_routing.py`

- [ ] **Step 1: Add integration-style unit tests**

Append to `tests/unit/test_vision_routing.py`:

```python
class TestImageControlGating:
    """UI control gating logic (no actual Qt, just config logic)."""

    def test_gating_disabled_when_untested(self):
        """Controls should NOT be disabled when vision_detected is None."""
        cfg = AppConfig()
        # vision_detected=None, no fallback
        should_disable = (cfg.vision_detected is not None
                          and not cfg.supports_vision
                          and not hasattr(cfg, '_vision_fallback_tool'))
        assert should_disable is False  # optimistic for untested

    def test_gating_disabled_when_no_vision_no_fallback(self):
        cfg = AppConfig()
        cfg.vision_detected = False
        cfg._vision_fallback_tool = None
        should_disable = (cfg.vision_detected is not None
                          and not cfg.supports_vision
                          and cfg._vision_fallback_tool is None)
        assert should_disable is True

    def test_gating_enabled_when_fallback_exists(self):
        cfg = AppConfig()
        cfg.vision_detected = False
        cfg._vision_fallback_tool = "server__describe_image"
        should_disable = (cfg.vision_detected is not None
                          and not cfg.supports_vision
                          and cfg._vision_fallback_tool is None)
        assert should_disable is False

    def test_gating_enabled_when_vision_supported(self):
        cfg = AppConfig()
        cfg.vision_detected = True
        should_disable = (cfg.vision_detected is not None
                          and not cfg.supports_vision)
        assert should_disable is False
```

- [ ] **Step 2: Run all vision routing tests**

Run: `.venv/bin/pytest tests/unit/test_vision_routing.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/unit/ -v`
Expected: All tests pass, no regressions

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_vision_routing.py
git commit -m "test: add image control gating tests for vision routing"
```

- [ ] **Step 5: Final commit with spec update**

Update `docs/specs/2026-03-13-vision-routing-design.md` status to "Implemented":

```bash
git add docs/specs/2026-03-13-vision-routing-design.md
git commit -m "docs: mark vision routing spec as implemented"
```
