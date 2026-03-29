"""Resolve the document the user is actually editing.

FreeCAD can desynchronize ``App.ActiveDocument`` from the document shown in the
GUI (e.g. another tab is focused in the MDI). Tools and ``execute_code`` must
target the same ``App::Document`` as the visible window — prefer
``FreeCADGui.ActiveDocument.Document`` when available.
"""


def resolve_active_document():
    """Return the ``App::Document`` to use for tools and code execution.

    Resolution order:

    1. ``FreeCADGui.ActiveDocument.Document`` when the GUI has an active view
    2. ``FreeCAD.ActiveDocument``

    Returns ``None`` if no document is available.
    """
    try:
        import FreeCAD as App
    except ImportError:
        return None

    try:
        import FreeCADGui as Gui
        gdoc = getattr(Gui, "ActiveDocument", None)
        if gdoc is not None:
            inner = getattr(gdoc, "Document", None)
            if inner is not None:
                return inner
    except Exception:
        pass

    try:
        return App.ActiveDocument if App.ActiveDocument else None
    except Exception:
        return None


def sync_app_active_document(doc) -> None:
    """Align ``App.ActiveDocument`` with *doc* so scripts using it hit the same file."""
    if doc is None:
        return
    try:
        import FreeCAD as App
        App.setActiveDocument(doc.Name)
    except Exception:
        pass


def refresh_gui_for_document(doc) -> None:
    """Best-effort GUI refresh after the document changes."""
    if doc is None:
        return
    try:
        import FreeCAD as App
        import FreeCADGui as Gui
        App.setActiveDocument(doc.Name)
        if hasattr(Gui, "updateGui"):
            Gui.updateGui()
    except Exception:
        pass


def get_synced_active_document():
    """Return :func:`resolve_active_document` and sync ``App`` to match."""
    doc = resolve_active_document()
    if doc is not None:
        sync_app_active_document(doc)
    return doc
