"""Integration test for sandbox post-execution validation.

Regression test for a false-positive in _sandbox_test: code that produced
FreeCAD C++ console errors (e.g. "PositionBySupport: AttachEngine3D: subshape
not found") or built null/invalid shapes was reported as safe because no
Python exception was raised during recompute.
"""

import pytest

from freecad_ai.core.executor import _sandbox_test, _find_freecad_cmd

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def freecad_available():
    if not _find_freecad_cmd():
        pytest.skip("No FreeCAD binary available for sandbox tests")


class TestSandboxPostExecValidation:
    def test_valid_partdesign_body_passes(self, freecad_available):
        # Positive control — a clean PartDesign body must still pass.
        code = (
            "body = doc.addObject('PartDesign::Body', 'Body')\n"
            "box = body.newObject('PartDesign::AdditiveBox', 'Box')\n"
        )
        ok, err = _sandbox_test(code, timeout=30)
        assert ok is True, "Valid code should pass sandbox; got err=" + err

    def test_bad_attachment_face_is_caught(self, freecad_available):
        # Attaching a sketch to a face that doesn't exist — the exact class
        # of failure that slipped through before: no Python exception, but
        # the Report View fills with PositionBySupport errors and the sketch
        # ends up in an invalid state.
        code = (
            "body = doc.addObject('PartDesign::Body', 'Body')\n"
            "box = body.newObject('PartDesign::AdditiveBox', 'Box')\n"
            "doc.recompute()\n"
            "sketch = body.newObject('Sketcher::SketchObject', 'Sketch')\n"
            "sketch.AttachmentSupport = [(box, 'Face99')]\n"
            "sketch.MapMode = 'FlatFace'\n"
        )
        ok, err = _sandbox_test(code, timeout=30)
        assert ok is False, "Sandbox should catch bad attachment"
        assert err, "Sandbox failure must include a reason"
