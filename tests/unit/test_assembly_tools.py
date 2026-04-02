"""Tests for assembly tool definitions and face placement helper."""

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from freecad_ai.tools.freecad_tools import (
    CREATE_ASSEMBLY,
    ADD_ASSEMBLY_JOINT,
    ADD_PART_TO_ASSEMBLY,
    ALL_TOOLS,
)


class TestAssemblyToolDefinitions:
    """Verify assembly tool definitions are well-formed."""

    def test_create_assembly_in_all_tools(self):
        assert CREATE_ASSEMBLY in ALL_TOOLS

    def test_add_assembly_joint_in_all_tools(self):
        assert ADD_ASSEMBLY_JOINT in ALL_TOOLS

    def test_add_part_to_assembly_in_all_tools(self):
        assert ADD_PART_TO_ASSEMBLY in ALL_TOOLS

    def test_create_assembly_params(self):
        names = [p.name for p in CREATE_ASSEMBLY.parameters]
        assert "label" in names
        assert "part_names" in names

    def test_add_joint_params(self):
        names = [p.name for p in ADD_ASSEMBLY_JOINT.parameters]
        assert "assembly_name" in names
        assert "part1_name" in names
        assert "face1" in names
        assert "part2_name" in names
        assert "face2" in names
        assert "joint_type" in names

    def test_add_part_params(self):
        names = [p.name for p in ADD_PART_TO_ASSEMBLY.parameters]
        assert "assembly_name" in names
        assert "part_name" in names
        assert "position" in names

    def test_categories(self):
        assert CREATE_ASSEMBLY.category == "modeling"
        assert ADD_ASSEMBLY_JOINT.category == "modeling"
        assert ADD_PART_TO_ASSEMBLY.category == "modeling"

    def test_assembly_tools_before_select_geometry(self):
        names = [t.name for t in ALL_TOOLS]
        for tool_name in ["create_assembly", "add_assembly_joint", "add_part_to_assembly"]:
            assert names.index(tool_name) < names.index("select_geometry")


class TestAssemblyHelpers:
    """Test assembly helper functions."""

    def test_find_sub_name_exists(self):
        """_find_sub_name should be importable."""
        from freecad_ai.tools.freecad_tools import _find_sub_name
        assert callable(_find_sub_name)

    def test_find_sub_name_with_tip(self):
        """Should prefix with tip feature name for PartDesign bodies."""
        from freecad_ai.tools.freecad_tools import _find_sub_name
        part = MagicMock()
        part.Tip = MagicMock()
        part.Tip.Name = "Pad"
        assert _find_sub_name(part, "Face6") == "Pad.Face6"

    def test_find_sub_name_without_tip(self):
        """Should return face name as-is for non-PartDesign objects."""
        from freecad_ai.tools.freecad_tools import _find_sub_name
        part = MagicMock(spec=[])  # no Tip attribute
        assert _find_sub_name(part, "Face3") == "Face3"

    def test_setup_assembly_imports_exists(self):
        """_setup_assembly_imports should be importable."""
        from freecad_ai.tools.freecad_tools import _setup_assembly_imports
        assert callable(_setup_assembly_imports)

    def test_get_joint_group_exists(self):
        """_get_joint_group should be importable."""
        from freecad_ai.tools.freecad_tools import _get_joint_group
        assert callable(_get_joint_group)
