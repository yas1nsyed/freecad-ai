"""Tests for the new Part tools: wedge, scale, section, linear/polar patterns, view tools."""

import pytest

from freecad_ai.tools.registry import ToolParam, ToolRegistry
from freecad_ai.tools.freecad_tools import (
    ALL_TOOLS,
    CREATE_WEDGE,
    SCALE_OBJECT,
    SECTION_OBJECT,
    LINEAR_PATTERN,
    POLAR_PATTERN,
    SHELL_OBJECT,
    CAPTURE_VIEWPORT,
    SET_VIEW,
    ZOOM_OBJECT,
)


NEW_TOOLS = [CREATE_WEDGE, SCALE_OBJECT, SECTION_OBJECT, LINEAR_PATTERN, POLAR_PATTERN, SHELL_OBJECT]


class TestToolDefinitions:
    """Verify each new ToolDefinition has correct name, category, and params."""

    @pytest.mark.parametrize("tool,expected_name", [
        (CREATE_WEDGE, "create_wedge"),
        (SCALE_OBJECT, "scale_object"),
        (SECTION_OBJECT, "section_object"),
        (LINEAR_PATTERN, "linear_pattern"),
        (POLAR_PATTERN, "polar_pattern"),
        (SHELL_OBJECT, "shell_object"),
    ])
    def test_tool_names(self, tool, expected_name):
        assert tool.name == expected_name

    @pytest.mark.parametrize("tool", NEW_TOOLS)
    def test_category_is_modeling(self, tool):
        assert tool.category == "modeling"

    @pytest.mark.parametrize("tool", NEW_TOOLS)
    def test_handler_is_callable(self, tool):
        assert callable(tool.handler)

    @pytest.mark.parametrize("tool", NEW_TOOLS)
    def test_has_description(self, tool):
        assert len(tool.description) > 10

    def test_create_wedge_params(self):
        names = [p.name for p in CREATE_WEDGE.parameters]
        assert "length" in names
        assert "width" in names
        assert "height" in names
        assert "top_length" in names
        assert "top_width" in names
        # All optional (wedge has sensible defaults)
        for p in CREATE_WEDGE.parameters:
            assert p.required is False

    def test_scale_object_params(self):
        names = [p.name for p in SCALE_OBJECT.parameters]
        required = [p.name for p in SCALE_OBJECT.parameters if p.required]
        assert "object_name" in required
        assert "scale_x" in names
        assert "scale_y" in names
        assert "scale_z" in names
        assert "uniform" in names
        assert "copy" in names

    def test_section_object_params(self):
        names = [p.name for p in SECTION_OBJECT.parameters]
        required = [p.name for p in SECTION_OBJECT.parameters if p.required]
        assert "object_name" in required
        assert "tool_object" in names
        assert "plane" in names
        assert "offset" in names
        # plane should have enum
        plane_param = next(p for p in SECTION_OBJECT.parameters if p.name == "plane")
        assert plane_param.enum == ["XY", "XZ", "YZ"]

    def test_linear_pattern_params(self):
        names = [p.name for p in LINEAR_PATTERN.parameters]
        required = [p.name for p in LINEAR_PATTERN.parameters if p.required]
        assert "feature_name" in required
        assert "length" in required
        assert "occurrences" in required
        assert "direction" in names
        # occurrences should be integer type
        occ_param = next(p for p in LINEAR_PATTERN.parameters if p.name == "occurrences")
        assert occ_param.type == "integer"

    def test_polar_pattern_params(self):
        names = [p.name for p in POLAR_PATTERN.parameters]
        required = [p.name for p in POLAR_PATTERN.parameters if p.required]
        assert "feature_name" in required
        assert "occurrences" in required
        assert "axis" in names
        assert "angle" in names
        # angle default should be 360
        angle_param = next(p for p in POLAR_PATTERN.parameters if p.name == "angle")
        assert angle_param.default == 360.0

    def test_shell_object_params(self):
        names = [p.name for p in SHELL_OBJECT.parameters]
        required = [p.name for p in SHELL_OBJECT.parameters if p.required]
        assert "object_name" in required
        assert "faces" in names
        assert "thickness" in names
        assert "join" in names
        assert "reversed" in names
        assert "label" in names
        # thickness default should be 1.0
        thick_param = next(p for p in SHELL_OBJECT.parameters if p.name == "thickness")
        assert thick_param.default == 1.0
        # join should have enum
        join_param = next(p for p in SHELL_OBJECT.parameters if p.name == "join")
        assert join_param.enum == ["Arc", "Intersection"]
        # faces should be array of strings
        faces_param = next(p for p in SHELL_OBJECT.parameters if p.name == "faces")
        assert faces_param.type == "array"
        assert faces_param.items == {"type": "string"}


class TestAllToolsMembership:
    """Verify all new tools are in the ALL_TOOLS list."""

    @pytest.mark.parametrize("tool", NEW_TOOLS)
    def test_in_all_tools(self, tool):
        assert tool in ALL_TOOLS

    def test_select_geometry_is_last(self):
        """SELECT_GEOMETRY should remain the last tool."""
        assert ALL_TOOLS[-1].name == "select_geometry"

    def test_new_tools_before_select_geometry(self):
        """New tools should come before SELECT_GEOMETRY."""
        names = [t.name for t in ALL_TOOLS]
        for tool in NEW_TOOLS:
            assert names.index(tool.name) < names.index("select_geometry")


class TestSchemaGeneration:
    """Verify OpenAI schema includes the new tools."""

    def test_openai_schema_includes_new_tools(self):
        reg = ToolRegistry()
        for tool in ALL_TOOLS:
            reg.register(tool)
        schema = reg.to_openai_schema()
        schema_names = {s["function"]["name"] for s in schema}
        for tool in NEW_TOOLS:
            assert tool.name in schema_names

    def test_anthropic_schema_includes_new_tools(self):
        reg = ToolRegistry()
        for tool in ALL_TOOLS:
            reg.register(tool)
        schema = reg.to_anthropic_schema()
        schema_names = {s["name"] for s in schema}
        for tool in NEW_TOOLS:
            assert tool.name in schema_names


# ── View tool tests ────────────────────────────────────────

VIEW_TOOLS = [CAPTURE_VIEWPORT, SET_VIEW, ZOOM_OBJECT]


class TestViewToolDefinitions:
    """Verify view tool definitions have correct names, categories, and params."""

    @pytest.mark.parametrize("tool,expected_name", [
        (CAPTURE_VIEWPORT, "capture_viewport"),
        (SET_VIEW, "set_view"),
        (ZOOM_OBJECT, "zoom_object"),
    ])
    def test_tool_names(self, tool, expected_name):
        assert tool.name == expected_name

    @pytest.mark.parametrize("tool", VIEW_TOOLS)
    def test_category_is_view(self, tool):
        assert tool.category == "view"

    @pytest.mark.parametrize("tool", VIEW_TOOLS)
    def test_handler_is_callable(self, tool):
        assert callable(tool.handler)

    @pytest.mark.parametrize("tool", VIEW_TOOLS)
    def test_has_description(self, tool):
        assert len(tool.description) > 10

    def test_capture_viewport_params(self):
        names = [p.name for p in CAPTURE_VIEWPORT.parameters]
        required = [p.name for p in CAPTURE_VIEWPORT.parameters if p.required]
        assert "filepath" in required
        assert "width" in names
        assert "height" in names
        assert "background" in names
        # background should have enum
        bg_param = next(p for p in CAPTURE_VIEWPORT.parameters if p.name == "background")
        assert bg_param.enum == ["Current", "White", "Black", "Transparent"]
        # width/height should be optional integers
        w_param = next(p for p in CAPTURE_VIEWPORT.parameters if p.name == "width")
        assert w_param.type == "integer"
        assert w_param.required is False
        assert w_param.default == 800

    def test_set_view_params(self):
        names = [p.name for p in SET_VIEW.parameters]
        required = [p.name for p in SET_VIEW.parameters if p.required]
        assert "orientation" in required
        assert "fit_all" in names
        assert "projection" in names
        # orientation should have enum with all standard views
        orient_param = next(p for p in SET_VIEW.parameters if p.name == "orientation")
        assert "isometric" in orient_param.enum
        assert "front" in orient_param.enum
        assert "top" in orient_param.enum
        # projection should have enum
        proj_param = next(p for p in SET_VIEW.parameters if p.name == "projection")
        assert proj_param.enum == ["Orthographic", "Perspective"]

    def test_zoom_object_params(self):
        names = [p.name for p in ZOOM_OBJECT.parameters]
        required = [p.name for p in ZOOM_OBJECT.parameters if p.required]
        assert "object_name" in required
        assert len(ZOOM_OBJECT.parameters) == 1


class TestViewToolsInAllTools:
    """Verify view tools are in ALL_TOOLS and positioned correctly."""

    @pytest.mark.parametrize("tool", VIEW_TOOLS)
    def test_in_all_tools(self, tool):
        assert tool in ALL_TOOLS

    def test_view_tools_before_select_geometry(self):
        """View tools should come before SELECT_GEOMETRY."""
        names = [t.name for t in ALL_TOOLS]
        for tool in VIEW_TOOLS:
            assert names.index(tool.name) < names.index("select_geometry")


class TestViewToolsSchemaGeneration:
    """Verify view tools appear in OpenAI and Anthropic schemas."""

    def test_openai_schema_includes_view_tools(self):
        reg = ToolRegistry()
        for tool in ALL_TOOLS:
            reg.register(tool)
        schema = reg.to_openai_schema()
        schema_names = {s["function"]["name"] for s in schema}
        for tool in VIEW_TOOLS:
            assert tool.name in schema_names

    def test_anthropic_schema_includes_view_tools(self):
        reg = ToolRegistry()
        for tool in ALL_TOOLS:
            reg.register(tool)
        schema = reg.to_anthropic_schema()
        schema_names = {s["name"] for s in schema}
        for tool in VIEW_TOOLS:
            assert tool.name in schema_names
