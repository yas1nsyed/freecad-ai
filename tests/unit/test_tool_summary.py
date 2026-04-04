"""Tests for tool call summary rendering."""

import pytest

from freecad_ai.ui.message_view import render_tool_summary


class TestRenderToolSummary:
    def test_empty_timeline_returns_empty(self):
        assert render_tool_summary([]) == ""

    def test_single_success(self):
        timeline = [{"name": "create_body", "success": True, "elapsed": 0.05, "turn": 0}]
        html = render_tool_summary(timeline)
        assert "create_body" in html
        assert "1 tools" in html
        assert "50ms" in html

    def test_multiple_tools_shows_flow(self):
        timeline = [
            {"name": "create_body", "success": True, "elapsed": 0.05, "turn": 0},
            {"name": "create_sketch", "success": True, "elapsed": 0.1, "turn": 0},
            {"name": "pad_sketch", "success": True, "elapsed": 0.08, "turn": 1},
        ]
        html = render_tool_summary(timeline)
        assert "3 tools" in html
        assert "&rarr;" in html  # flow arrows
        assert "create_body" in html
        assert "create_sketch" in html
        assert "pad_sketch" in html

    def test_failure_counted(self):
        timeline = [
            {"name": "create_body", "success": True, "elapsed": 0.05, "turn": 0},
            {"name": "bad_tool", "success": False, "elapsed": 0.02, "turn": 0},
        ]
        html = render_tool_summary(timeline)
        assert "1 ok" in html
        assert "1 failed" in html
        assert "&#10007;" in html  # X mark for failure

    def test_timing_shows_seconds_for_slow(self):
        timeline = [{"name": "execute_code", "success": True, "elapsed": 2.5, "turn": 0}]
        html = render_tool_summary(timeline)
        assert "2.5s" in html

    def test_timing_shows_ms_for_fast(self):
        timeline = [{"name": "measure", "success": True, "elapsed": 0.015, "turn": 0}]
        html = render_tool_summary(timeline)
        assert "15ms" in html

    def test_total_time(self):
        timeline = [
            {"name": "a", "success": True, "elapsed": 1.0, "turn": 0},
            {"name": "b", "success": True, "elapsed": 2.0, "turn": 0},
        ]
        html = render_tool_summary(timeline)
        assert "3.0s" in html

    def test_html_escaping(self):
        timeline = [{"name": "<script>alert(1)</script>", "success": True, "elapsed": 0.01, "turn": 0}]
        html = render_tool_summary(timeline)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
