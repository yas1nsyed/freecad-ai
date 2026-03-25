"""Tests for _get_object name resolution and _suggest_similar hints."""

import types


def _make_doc(objects):
    """Create a fake FreeCAD document with the given objects.

    Each object is a dict with 'Name', 'Label', and optionally 'TypeId'.
    """
    doc_objects = []
    for spec in objects:
        obj = types.SimpleNamespace(
            Name=spec["Name"],
            Label=spec.get("Label", spec["Name"]),
            TypeId=spec.get("TypeId", "Part::Feature"),
        )
        doc_objects.append(obj)

    doc = types.SimpleNamespace(Objects=doc_objects)

    def getObject(name):
        for o in doc_objects:
            if o.Name == name:
                return o
        return None

    doc.getObject = getObject
    return doc


class TestGetObject:
    """Test the _get_object helper with LLM naming variant resolution."""

    def _get_object(self, doc, name):
        from freecad_ai.tools.freecad_tools import _get_object
        return _get_object(doc, name)

    def test_exact_name(self):
        doc = _make_doc([{"Name": "Sketch"}])
        assert self._get_object(doc, "Sketch").Name == "Sketch"

    def test_exact_name_with_suffix(self):
        doc = _make_doc([{"Name": "Sketch001"}])
        assert self._get_object(doc, "Sketch001").Name == "Sketch001"

    def test_label_fallback(self):
        doc = _make_doc([{"Name": "Body", "Label": "EnclosureBase"}])
        assert self._get_object(doc, "EnclosureBase").Name == "Body"

    def test_sketch0_resolves_to_sketch(self):
        """LLMs often use 'Sketch0' for the first sketch, but FreeCAD names it 'Sketch'."""
        doc = _make_doc([{"Name": "Sketch"}])
        assert self._get_object(doc, "Sketch0").Name == "Sketch"

    def test_sketch1_resolves_to_sketch001(self):
        """LLMs use 'Sketch1' but FreeCAD names it 'Sketch001'."""
        doc = _make_doc([{"Name": "Sketch001"}])
        assert self._get_object(doc, "Sketch1").Name == "Sketch001"

    def test_sketch2_resolves_to_sketch002(self):
        doc = _make_doc([{"Name": "Sketch002"}])
        assert self._get_object(doc, "Sketch2").Name == "Sketch002"

    def test_pad0_resolves_to_pad(self):
        doc = _make_doc([{"Name": "Pad"}])
        assert self._get_object(doc, "Pad0").Name == "Pad"

    def test_body1_resolves_to_body001(self):
        doc = _make_doc([{"Name": "Body001", "TypeId": "PartDesign::Body"}])
        assert self._get_object(doc, "Body1").Name == "Body001"

    def test_no_false_match(self):
        """'Sketch5' should not match 'Sketch' or 'Sketch001'."""
        doc = _make_doc([{"Name": "Sketch"}, {"Name": "Sketch001"}])
        assert self._get_object(doc, "Sketch5") is None

    def test_returns_none_for_nonexistent(self):
        doc = _make_doc([{"Name": "Sketch"}])
        assert self._get_object(doc, "Foobar") is None

    def test_label_variant_sketch0(self):
        """'Sketch0' matches an object labeled 'Sketch' even with different Name."""
        doc = _make_doc([{"Name": "Sketch", "Label": "Sketch"}])
        assert self._get_object(doc, "Sketch0").Name == "Sketch"


class TestSuggestSimilar:
    """Test the _suggest_similar helper for error hints."""

    def _suggest(self, doc, name, type_filter=None):
        from freecad_ai.tools.freecad_tools import _suggest_similar
        return _suggest_similar(doc, name, type_filter)

    def test_suggests_sketches(self):
        doc = _make_doc([
            {"Name": "Sketch", "TypeId": "Sketcher::SketchObject"},
            {"Name": "Sketch001", "TypeId": "Sketcher::SketchObject"},
            {"Name": "Body", "TypeId": "PartDesign::Body"},
        ])
        hint = self._suggest(doc, "Sketch5", "Sketcher")
        assert "Sketch" in hint
        assert "Sketch001" in hint
        assert "Body" not in hint

    def test_suggests_bodies(self):
        doc = _make_doc([
            {"Name": "Body", "TypeId": "PartDesign::Body"},
            {"Name": "Body001", "TypeId": "PartDesign::Body"},
            {"Name": "Sketch", "TypeId": "Sketcher::SketchObject"},
        ])
        hint = self._suggest(doc, "Body5", "Body")
        assert "Body" in hint
        assert "Body001" in hint
        assert "Sketch" not in hint

    def test_empty_when_no_objects(self):
        doc = _make_doc([])
        hint = self._suggest(doc, "Sketch0")
        assert hint == ""

    def test_no_type_filter_lists_all(self):
        doc = _make_doc([
            {"Name": "Pad", "TypeId": "PartDesign::Pad"},
            {"Name": "Pocket", "TypeId": "PartDesign::Pocket"},
        ])
        hint = self._suggest(doc, "Pad5")
        assert "Pad" in hint
