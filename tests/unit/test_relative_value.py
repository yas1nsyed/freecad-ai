"""Tests for _resolve_relative_value used in modify_property."""

import pytest

from freecad_ai.tools.freecad_tools import _resolve_relative_value


class TestResolveRelativeValue:
    def test_absolute_number_passthrough(self):
        assert _resolve_relative_value(50, 100) == 100

    def test_absolute_string_number(self):
        # Non-relative string stays as-is (modify_property handles conversion)
        assert _resolve_relative_value(50, "100") == "100"

    def test_percentage_increase(self):
        result = _resolve_relative_value(100, "+10%")
        assert result == pytest.approx(110.0)

    def test_percentage_decrease(self):
        result = _resolve_relative_value(100, "-20%")
        assert result == pytest.approx(80.0)

    def test_percentage_zero(self):
        result = _resolve_relative_value(50, "+0%")
        assert result == pytest.approx(50.0)

    def test_multiply(self):
        result = _resolve_relative_value(100, "*1.5")
        assert result == pytest.approx(150.0)

    def test_multiply_double(self):
        result = _resolve_relative_value(30, "*2")
        assert result == pytest.approx(60.0)

    def test_add(self):
        result = _resolve_relative_value(50, "+5")
        assert result == pytest.approx(55.0)

    def test_subtract(self):
        result = _resolve_relative_value(50, "-3")
        assert result == pytest.approx(47.0)

    def test_non_numeric_current_returns_expr(self):
        assert _resolve_relative_value("hello", "+10%") == "+10%"

    def test_empty_string(self):
        assert _resolve_relative_value(50, "") == ""

    def test_bool_passthrough(self):
        assert _resolve_relative_value(True, False) is False

    def test_percentage_with_float_current(self):
        result = _resolve_relative_value(2.5, "+10%")
        assert result == pytest.approx(2.75)
