"""Tests for i18n fallback behavior (no FreeCAD/PySide available)."""

from freecad_ai.i18n import QT_TRANSLATE_NOOP, translate


class TestTranslateFallback:
    def test_translate_returns_text(self):
        result = translate("Context", "Hello World")
        assert result == "Hello World"

    def test_translate_ignores_context(self):
        result = translate("AnyContext", "message")
        assert result == "message"

    def test_qt_translate_noop_returns_text(self):
        result = QT_TRANSLATE_NOOP("Context", "Some text")
        assert result == "Some text"
