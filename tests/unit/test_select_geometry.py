"""Tests for the select_geometry tool definition and handler."""

import sys
import types

import pytest
from unittest.mock import patch, MagicMock

from freecad_ai.tools.registry import ToolParam, ToolRegistry, ToolResult


# ---------- Import the tool definition without triggering FreeCAD ----------

from freecad_ai.tools.freecad_tools import SELECT_GEOMETRY


class TestSelectGeometryDefinition:
    def test_name(self):
        assert SELECT_GEOMETRY.name == "select_geometry"

    def test_category(self):
        assert SELECT_GEOMETRY.category == "interactive"

    def test_has_prompt_param(self):
        names = [p.name for p in SELECT_GEOMETRY.parameters]
        assert "prompt" in names

    def test_has_select_type_param_with_enum(self):
        param = next(p for p in SELECT_GEOMETRY.parameters if p.name == "select_type")
        assert param.enum == ["any", "edge", "face", "vertex"]
        assert param.required is False
        assert param.default == "any"

    def test_has_max_count_param(self):
        param = next(p for p in SELECT_GEOMETRY.parameters if p.name == "max_count")
        assert param.type == "integer"
        assert param.required is False
        assert param.default == 0

    def test_all_params_optional(self):
        for p in SELECT_GEOMETRY.parameters:
            assert p.required is False, f"{p.name} should be optional"


class TestSelectGeometryInRegistry:
    def test_registered_in_all_tools(self):
        from freecad_ai.tools.freecad_tools import ALL_TOOLS
        names = [t.name for t in ALL_TOOLS]
        assert "select_geometry" in names

    def test_openai_schema(self):
        reg = ToolRegistry()
        reg.register(SELECT_GEOMETRY)
        schema = reg.to_openai_schema()
        assert len(schema) == 1
        func = schema[0]["function"]
        assert func["name"] == "select_geometry"
        props = func["parameters"]["properties"]
        assert "prompt" in props
        assert "select_type" in props
        assert "max_count" in props

    def test_anthropic_schema(self):
        reg = ToolRegistry()
        reg.register(SELECT_GEOMETRY)
        schema = reg.to_anthropic_schema()
        assert len(schema) == 1
        assert schema[0]["name"] == "select_geometry"
        props = schema[0]["input_schema"]["properties"]
        assert "select_type" in props
        assert props["select_type"]["enum"] == ["any", "edge", "face", "vertex"]


class TestSelectGeometryHandler:
    def _patch_selection_panel(self, mock_panel):
        """Stub the UI module so tests run without Qt / real SelectionPanel."""
        fake_mod = types.ModuleType("freecad_ai.ui.selection_panel")
        fake_mod.SelectionPanel = MagicMock(return_value=mock_panel)
        return patch.dict(sys.modules, {"freecad_ai.ui.selection_panel": fake_mod})

    def test_cancelled_returns_empty(self):
        """Handler returns graceful message when user cancels."""
        mock_panel = MagicMock()
        mock_panel.exec.return_value = []

        with self._patch_selection_panel(mock_panel):
            from freecad_ai.tools.freecad_tools import _handle_select_geometry
            result = _handle_select_geometry(prompt="Pick edges")

        assert result.success is True
        assert result.data["selections"] == []
        assert "cancelled" in result.output.lower() or "nothing" in result.output.lower()

    def test_with_selections(self):
        """Handler formats selections correctly."""
        sample = [
            {"object": "Pad", "sub_element": "Edge1", "point": [10.0, 0.0, 5.0]},
            {"object": "Pad", "sub_element": "Edge4", "point": [0.0, 20.0, 5.0]},
        ]
        mock_panel = MagicMock()
        mock_panel.exec.return_value = sample

        with self._patch_selection_panel(mock_panel):
            from freecad_ai.tools.freecad_tools import _handle_select_geometry
            result = _handle_select_geometry(
                prompt="Select edges to fillet", select_type="edge"
            )

        assert result.success is True
        assert len(result.data["selections"]) == 2
        assert "Pad.Edge1" in result.output
        assert "Pad.Edge4" in result.output
        assert "10.00" in result.output
