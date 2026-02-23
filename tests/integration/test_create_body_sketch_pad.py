"""Integration tests for create_body, create_sketch, and pad_sketch tools."""

import pytest

pytestmark = pytest.mark.integration


class TestCreateBody:
    def test_creates_partdesign_body(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_body

r = _handle_create_body(label="TestBody")
doc.recompute()
body = doc.getObject(r.data["name"])
results["data"] = {
    "success": r.success,
    "name": body.Name,
    "label": body.Label,
    "type_id": body.TypeId,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["type_id"] == "PartDesign::Body"
        assert d["label"] == "TestBody"


class TestCreateSketch:
    def test_sketch_with_rectangle(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_body, _handle_create_sketch

body_r = _handle_create_body(label="Body")
doc.recompute()
body_name = body_r.data["name"]

sketch_r = _handle_create_sketch(
    body_name=body_name,
    plane="XY",
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 30}],
)
doc.recompute()
sketch = doc.getObject(sketch_r.data["name"])
results["data"] = {
    "success": sketch_r.success,
    "geo_count": sketch.GeometryCount,
    "constraint_count": sketch.ConstraintCount,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["geo_count"] == 4  # Rectangle = 4 lines
        assert d["constraint_count"] >= 8  # 4 coincident + 2 horizontal + 2 vertical

    def test_sketch_with_circle(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_body, _handle_create_sketch

body_r = _handle_create_body(label="Body")
doc.recompute()

sketch_r = _handle_create_sketch(
    body_name=body_r.data["name"],
    geometries=[{"type": "circle", "cx": 0, "cy": 0, "radius": 15}],
)
doc.recompute()
sketch = doc.getObject(sketch_r.data["name"])
results["data"] = {
    "success": sketch_r.success,
    "geo_count": sketch.GeometryCount,
}
""")
        assert result["ok"]
        assert result["data"]["geo_count"] == 1

    def test_sketch_with_offset(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_body, _handle_create_sketch

body_r = _handle_create_body(label="Body")
doc.recompute()

sketch_r = _handle_create_sketch(
    body_name=body_r.data["name"],
    plane="XY",
    offset=25.0,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10}],
)
doc.recompute()
sketch = doc.getObject(sketch_r.data["name"])
z_offset = sketch.AttachmentOffset.Base.z
results["data"] = {
    "success": sketch_r.success,
    "z_offset": z_offset,
}
""")
        assert result["ok"]
        assert result["data"]["z_offset"] == 25.0


class TestPadSketch:
    def test_pad_creates_solid(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_body, _handle_create_sketch, _handle_pad_sketch

body_r = _handle_create_body(label="Body")
doc.recompute()
body_name = body_r.data["name"]

sketch_r = _handle_create_sketch(
    body_name=body_name,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 40, "height": 30}],
)
doc.recompute()

pad_r = _handle_pad_sketch(sketch_name=sketch_r.data["name"], length=20)
doc.recompute()

body = doc.getObject(body_name)
results["data"] = {
    "pad_success": pad_r.success,
    "volume": body.Shape.Volume,
    "expected_volume": 40 * 30 * 20,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["pad_success"]
        assert abs(d["volume"] - d["expected_volume"]) < 10.0

    def test_pad_symmetric(self, run_freecad_script):
        """Symmetric pad extends equally in both directions (uses Midplane)."""
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_body, _handle_create_sketch, _handle_pad_sketch

body_r = _handle_create_body(label="Body")
doc.recompute()
body_name = body_r.data["name"]

sketch_r = _handle_create_sketch(
    body_name=body_name,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 20, "height": 20}],
)
doc.recompute()

pad_r = _handle_pad_sketch(sketch_name=sketch_r.data["name"], length=10, symmetric=True)
doc.recompute()

body = doc.getObject(body_name)
bb = body.Shape.BoundBox
results["data"] = {
    "success": pad_r.success,
    "error": pad_r.error,
    "z_min": bb.ZMin,
    "z_max": bb.ZMax,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"], f"Pad failed: {d.get('error', '')}"
        # Symmetric pad: extends 5mm in each direction
        assert abs(d["z_min"] - (-5.0)) < 0.1
        assert abs(d["z_max"] - 5.0) < 0.1
