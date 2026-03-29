"""Unit tests for GUI-aligned active document resolution."""

import sys
import unittest
from unittest.mock import MagicMock, patch


class TestActiveDocument(unittest.TestCase):
    def test_resolve_prefers_gui_active_document(self):
        inner = MagicMock()
        inner.Name = "GuiDoc"
        gdoc = MagicMock()
        gdoc.Document = inner
        app_mod = MagicMock()
        app_mod.ActiveDocument = MagicMock(name="wrong_app_doc")

        gui_mod = MagicMock()
        gui_mod.ActiveDocument = gdoc

        with patch.dict(sys.modules, {"FreeCAD": app_mod, "FreeCADGui": gui_mod}):
            from freecad_ai.core import active_document

            self.assertIs(active_document.resolve_active_document(), inner)

    def test_get_synced_calls_set_active_document(self):
        inner = MagicMock()
        inner.Name = "SyncedDoc"
        gdoc = MagicMock()
        gdoc.Document = inner
        app_mod = MagicMock()
        app_mod.ActiveDocument = None
        gui_mod = MagicMock()
        gui_mod.ActiveDocument = gdoc

        with patch.dict(sys.modules, {"FreeCAD": app_mod, "FreeCADGui": gui_mod}):
            from freecad_ai.core import active_document

            out = active_document.get_synced_active_document()
            self.assertIs(out, inner)
            app_mod.setActiveDocument.assert_called_once_with("SyncedDoc")

    def test_resolve_falls_back_to_app_when_gui_has_no_document(self):
        app_doc = MagicMock()
        app_mod = MagicMock()
        app_mod.ActiveDocument = app_doc
        gui_mod = MagicMock()
        gactive = MagicMock()
        gactive.Document = None
        gui_mod.ActiveDocument = gactive

        with patch.dict(sys.modules, {"FreeCAD": app_mod, "FreeCADGui": gui_mod}):
            from freecad_ai.core import active_document

            self.assertIs(active_document.resolve_active_document(), app_doc)

    def test_resolve_falls_back_when_no_freecadgui(self):
        app_doc = MagicMock()
        app_mod = MagicMock()
        app_mod.ActiveDocument = app_doc

        import builtins

        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "FreeCADGui":
                raise ImportError("no gui")
            return real_import(name, globals, locals, fromlist, level)

        with patch.dict(sys.modules, {"FreeCAD": app_mod}):
            from freecad_ai.core import active_document

            with patch.object(builtins, "__import__", side_effect=fake_import):
                self.assertIs(active_document.resolve_active_document(), app_doc)

    def test_resolve_returns_none_when_no_document(self):
        app_mod = MagicMock()
        app_mod.ActiveDocument = None
        gui_mod = MagicMock()
        gui_mod.ActiveDocument = None

        with patch.dict(sys.modules, {"FreeCAD": app_mod, "FreeCADGui": gui_mod}):
            from freecad_ai.core import active_document

            self.assertIsNone(active_document.resolve_active_document())


if __name__ == "__main__":
    unittest.main()
