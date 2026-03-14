"""Tests for tools setup."""


class TestCreateDefaultRegistryExtraTools:
    def test_extra_tools_empty_by_default(self):
        from freecad_ai.tools.setup import create_default_registry
        registry = create_default_registry(include_mcp=False)
        assert registry is not None

    def test_extra_tools_registered(self):
        from freecad_ai.tools.setup import create_default_registry
        from freecad_ai.tools.registry import ToolDefinition, ToolParam, ToolResult
        extra = ToolDefinition(
            name="test_extra_tool",
            description="A test tool",
            parameters=[],
            handler=lambda: ToolResult(success=True, output="ok"),
        )
        registry = create_default_registry(include_mcp=False, extra_tools=[extra])
        tool = registry.get("test_extra_tool")
        assert tool is not None
        assert tool.name == "test_extra_tool"
