"""Integration tests for pocket_sketch — including auto-direction bug fix."""

import pytest

pytestmark = pytest.mark.integration


class TestPocketSketch:
    def test_pocket_reduces_volume(self, run_freecad_script):
        """Basic pocket: volume should decrease after pocketing."""
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import (
    _handle_create_body, _handle_create_sketch,
    _handle_pad_sketch, _handle_pocket_sketch,
)

# Create a solid block 50x40x30
body_r = _handle_create_body(label="Body")
doc.recompute()
body_name = body_r.data["name"]

sketch_r = _handle_create_sketch(
    body_name=body_name,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 40}],
)
doc.recompute()

pad_r = _handle_pad_sketch(sketch_name=sketch_r.data["name"], length=30)
doc.recompute()

body = doc.getObject(body_name)
vol_before = body.Shape.Volume

# Pocket from the top face (offset=30) with a smaller rectangle
pocket_sketch_r = _handle_create_sketch(
    body_name=body_name,
    plane="XY",
    offset=30.0,
    geometries=[{"type": "rectangle", "x": 5, "y": 5, "width": 40, "height": 30}],
)
doc.recompute()

pocket_r = _handle_pocket_sketch(
    sketch_name=pocket_sketch_r.data["name"],
    length=25.0,
)
doc.recompute()

vol_after = body.Shape.Volume

results["data"] = {
    "pocket_success": pocket_r.success,
    "vol_before": vol_before,
    "vol_after": vol_after,
    "volume_removed": vol_before - vol_after,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["pocket_success"]
        assert d["vol_after"] < d["vol_before"]
        assert d["volume_removed"] > 1000  # Significant material removed

    def test_pocket_from_top_face_auto_direction(self, run_freecad_script):
        """Regression test: pocket from offset=H should cut downward into the solid."""
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import (
    _handle_create_body, _handle_create_sketch,
    _handle_pad_sketch, _handle_pocket_sketch,
)

H = 30  # height
T = 2   # wall thickness

# Create enclosure base: 80x60xH
body_r = _handle_create_body(label="Base")
doc.recompute()
body_name = body_r.data["name"]

outer_sketch = _handle_create_sketch(
    body_name=body_name,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 80, "height": 60}],
)
doc.recompute()

_handle_pad_sketch(sketch_name=outer_sketch.data["name"], length=H)
doc.recompute()

body = doc.getObject(body_name)
vol_solid = body.Shape.Volume

# Pocket from top: sketch at z=H, pocket depth = H-T
inner_sketch = _handle_create_sketch(
    body_name=body_name,
    plane="XY",
    offset=float(H),
    geometries=[{"type": "rectangle", "x": T, "y": T, "width": 80-2*T, "height": 60-2*T}],
)
doc.recompute()

pocket_r = _handle_pocket_sketch(
    sketch_name=inner_sketch.data["name"],
    length=float(H - T),
)
doc.recompute()

vol_hollow = body.Shape.Volume
bb = body.Shape.BoundBox

results["data"] = {
    "success": pocket_r.success,
    "vol_solid": vol_solid,
    "vol_hollow": vol_hollow,
    "has_floor": vol_hollow > 0,
    "z_min": bb.ZMin,
    "z_max": bb.ZMax,
    "is_hollow": vol_hollow < vol_solid * 0.5,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["has_floor"], "Pocket should leave a floor (volume > 0)"
        assert d["is_hollow"], "Pocket should hollow out most of the solid"
        assert abs(d["z_min"] - 0.0) < 0.1, "Bottom should be at z=0"
        assert abs(d["z_max"] - 30.0) < 0.1, "Top should be at z=30"

    def test_pocket_through_all(self, run_freecad_script):
        """Through-all pocket should cut completely through."""
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import (
    _handle_create_body, _handle_create_sketch,
    _handle_pad_sketch, _handle_pocket_sketch,
)

body_r = _handle_create_body(label="Body")
doc.recompute()
body_name = body_r.data["name"]

sketch_r = _handle_create_sketch(
    body_name=body_name,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": 40, "height": 40}],
)
doc.recompute()

_handle_pad_sketch(sketch_name=sketch_r.data["name"], length=20)
doc.recompute()

body = doc.getObject(body_name)
vol_before = body.Shape.Volume

# Circular through-all hole
hole_sketch = _handle_create_sketch(
    body_name=body_name,
    plane="XY",
    offset=20.0,
    geometries=[{"type": "circle", "cx": 20, "cy": 20, "radius": 5}],
)
doc.recompute()

pocket_r = _handle_pocket_sketch(
    sketch_name=hole_sketch.data["name"],
    through_all=True,
)
doc.recompute()

vol_after = body.Shape.Volume

results["data"] = {
    "success": pocket_r.success,
    "vol_before": vol_before,
    "vol_after": vol_after,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["vol_after"] < d["vol_before"]
