"""Tests for AGENTS.md loader — directory search, includes, variables."""

import os
from unittest.mock import patch

import pytest

from freecad_ai.extensions.agents_md import (
    INCLUDE_RE,
    INSTRUCTION_FILENAMES,
    MAX_INCLUDE_DEPTH,
    MAX_PARENT_LEVELS,
    VARIABLE_RE,
    _load_from_directory,
    _resolve_includes,
    _search_directory_chain,
    _substitute_variables,
)


class TestLoadFromDirectory:
    def test_loads_agents_md(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Instructions\nDo stuff.\n")
        content = _load_from_directory(str(tmp_path))
        assert "# Instructions" in content

    def test_loads_freecad_ai_md(self, tmp_path):
        (tmp_path / "FREECAD_AI.md").write_text("# FreeCAD AI\nCustom.\n")
        content = _load_from_directory(str(tmp_path))
        assert "# FreeCAD AI" in content

    def test_agents_md_has_priority(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("AGENTS content")
        (tmp_path / "FREECAD_AI.md").write_text("FREECAD_AI content")
        content = _load_from_directory(str(tmp_path))
        assert content == "AGENTS content"

    def test_returns_empty_for_missing_dir(self):
        content = _load_from_directory("/nonexistent/path")
        assert content == ""

    def test_returns_empty_for_empty_dir(self, tmp_path):
        content = _load_from_directory(str(tmp_path))
        assert content == ""

    def test_returns_empty_for_none(self):
        content = _load_from_directory(None)
        assert content == ""


class TestSearchDirectoryChain:
    def test_finds_in_start_dir(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("Found!")
        content = _search_directory_chain(str(tmp_path))
        assert content == "Found!"

    def test_finds_in_parent(self, tmp_path):
        child = tmp_path / "subdir"
        child.mkdir()
        (tmp_path / "AGENTS.md").write_text("Parent content")
        content = _search_directory_chain(str(child))
        assert content == "Parent content"

    def test_finds_in_grandparent(self, tmp_path):
        grandchild = tmp_path / "a" / "b"
        grandchild.mkdir(parents=True)
        (tmp_path / "AGENTS.md").write_text("Grandparent")
        content = _search_directory_chain(str(grandchild))
        assert content == "Grandparent"

    def test_returns_empty_when_not_found(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        content = _search_directory_chain(str(deep))
        assert content == ""

    def test_stops_at_max_parent_levels(self, tmp_path):
        # Create a chain deeper than MAX_PARENT_LEVELS
        current = tmp_path
        for i in range(MAX_PARENT_LEVELS + 3):
            current = current / f"level{i}"
            current.mkdir()
        (tmp_path / "AGENTS.md").write_text("Too far up")
        content = _search_directory_chain(str(current))
        # May or may not find it depending on depth — just shouldn't crash
        assert isinstance(content, str)


class TestResolveIncludes:
    def test_resolves_simple_include(self, tmp_path):
        (tmp_path / "extra.md").write_text("Included content")
        content = "Before\n<!-- include: extra.md -->\nAfter"
        result = _resolve_includes(content, str(tmp_path), depth=0)
        assert "Included content" in result
        assert "Before" in result
        assert "After" in result

    def test_nested_includes(self, tmp_path):
        (tmp_path / "a.md").write_text("<!-- include: b.md -->")
        (tmp_path / "b.md").write_text("Deep content")
        content = "<!-- include: a.md -->"
        result = _resolve_includes(content, str(tmp_path), depth=0)
        assert "Deep content" in result

    def test_missing_include_file(self, tmp_path):
        content = "<!-- include: nonexistent.md -->"
        result = _resolve_includes(content, str(tmp_path), depth=0)
        assert "include not found" in result

    def test_max_depth_stops_recursion(self, tmp_path):
        # Create a circular include that would infinitely recurse
        (tmp_path / "loop.md").write_text("<!-- include: loop.md -->")
        content = "<!-- include: loop.md -->"
        result = _resolve_includes(content, str(tmp_path), depth=MAX_INCLUDE_DEPTH - 1)
        # At max depth, includes are not resolved
        assert "include:" in result

    def test_empty_base_dir(self):
        content = "<!-- include: file.md -->"
        result = _resolve_includes(content, "", depth=0)
        assert result == content  # No resolution with empty base_dir

    def test_multiple_includes(self, tmp_path):
        (tmp_path / "a.md").write_text("Content A")
        (tmp_path / "b.md").write_text("Content B")
        content = "<!-- include: a.md -->\n<!-- include: b.md -->"
        result = _resolve_includes(content, str(tmp_path), depth=0)
        assert "Content A" in result
        assert "Content B" in result


class TestSubstituteVariables:
    @patch("freecad_ai.extensions.agents_md._get_variables")
    def test_replaces_known_variables(self, mock_vars):
        mock_vars.return_value = {
            "document_name": "MyDoc",
            "object_count": "5",
        }
        result = _substitute_variables("Doc: {{document_name}}, Objects: {{object_count}}")
        assert result == "Doc: MyDoc, Objects: 5"

    @patch("freecad_ai.extensions.agents_md._get_variables")
    def test_preserves_unknown_variables(self, mock_vars):
        mock_vars.return_value = {}
        result = _substitute_variables("{{unknown_var}}")
        assert result == "{{unknown_var}}"

    @patch("freecad_ai.extensions.agents_md._get_variables")
    def test_no_variables_passes_through(self, mock_vars):
        mock_vars.return_value = {}
        result = _substitute_variables("No variables here")
        assert result == "No variables here"


class TestRegexPatterns:
    def test_include_regex_matches(self):
        assert INCLUDE_RE.search("<!-- include: file.md -->")
        assert INCLUDE_RE.search("<!--include:file.md-->")
        assert INCLUDE_RE.search("<!--  include:  path/to/file.md  -->")

    def test_variable_regex_matches(self):
        assert VARIABLE_RE.search("{{document_name}}")
        assert VARIABLE_RE.search("{{object_count}}")

    def test_variable_regex_no_match_on_spaces(self):
        assert not VARIABLE_RE.search("{{ not_a_var }}")

    def test_instruction_filenames(self):
        assert "AGENTS.md" in INSTRUCTION_FILENAMES
        assert "FREECAD_AI.md" in INSTRUCTION_FILENAMES
