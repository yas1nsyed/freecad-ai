"""Tests for variable set and expression tools."""

from freecad_ai.tools.freecad_tools import (
    CREATE_VARIABLE_SET, SET_EXPRESSION, ALL_TOOLS,
)


class TestCreateVariableSetDefinition:
    def test_name(self):
        assert CREATE_VARIABLE_SET.name == "create_variable_set"

    def test_category(self):
        assert CREATE_VARIABLE_SET.category == "modeling"

    def test_has_variables_param(self):
        names = [p.name for p in CREATE_VARIABLE_SET.parameters]
        assert "variables" in names

    def test_has_label_param(self):
        names = [p.name for p in CREATE_VARIABLE_SET.parameters]
        assert "label" in names

    def test_in_all_tools(self):
        assert CREATE_VARIABLE_SET in ALL_TOOLS


class TestSetExpressionDefinition:
    def test_name(self):
        assert SET_EXPRESSION.name == "set_expression"

    def test_category(self):
        assert SET_EXPRESSION.category == "modeling"

    def test_has_required_params(self):
        names = [p.name for p in SET_EXPRESSION.parameters]
        assert "object_name" in names
        assert "property_name" in names
        assert "expression" in names

    def test_in_all_tools(self):
        assert SET_EXPRESSION in ALL_TOOLS

    def test_description_mentions_variables(self):
        assert "Variables" in SET_EXPRESSION.description
