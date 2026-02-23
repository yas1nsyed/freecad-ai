"""Integration tests for boolean_operation and transform_object tools."""

import pytest

pytestmark = pytest.mark.integration


class TestBooleanOperation:
    def test_fuse_increases_volume(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive, _handle_boolean_operation

_handle_create_primitive(shape_type="box", label="A", length=10, width=10, height=10)
_handle_create_primitive(shape_type="box", label="B", length=10, width=10, height=10, x=5)
doc.recompute()

vol_a = doc.getObject("A").Shape.Volume
vol_b = doc.getObject("B").Shape.Volume

r = _handle_boolean_operation(operation="fuse", object1="A", object2="B")
doc.recompute()

fused = doc.getObject(r.data["name"])
results["data"] = {
    "success": r.success,
    "vol_a": vol_a,
    "vol_b": vol_b,
    "vol_fused": fused.Shape.Volume,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        # Fuse of overlapping boxes: vol < vol_a + vol_b (overlap removed)
        assert d["vol_fused"] < d["vol_a"] + d["vol_b"]
        assert d["vol_fused"] > d["vol_a"]

    def test_cut_reduces_volume(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive, _handle_boolean_operation

_handle_create_primitive(shape_type="box", label="Base", length=20, width=20, height=20)
_handle_create_primitive(shape_type="box", label="Tool", length=10, width=10, height=10, x=5, y=5, z=5)
doc.recompute()

vol_before = doc.getObject("Base").Shape.Volume

r = _handle_boolean_operation(operation="cut", object1="Base", object2="Tool")
doc.recompute()

cut_obj = doc.getObject(r.data["name"])
results["data"] = {
    "success": r.success,
    "vol_before": vol_before,
    "vol_after": cut_obj.Shape.Volume,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["vol_after"] < d["vol_before"]

    def test_common_intersection(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive, _handle_boolean_operation

_handle_create_primitive(shape_type="box", label="A", length=10, width=10, height=10)
_handle_create_primitive(shape_type="box", label="B", length=10, width=10, height=10, x=5, y=5)
doc.recompute()

r = _handle_boolean_operation(operation="common", object1="A", object2="B")
doc.recompute()

common_obj = doc.getObject(r.data["name"])
results["data"] = {
    "success": r.success,
    "volume": common_obj.Shape.Volume,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        # Common of 5mm overlap: 5*5*10 = 250
        assert abs(d["volume"] - 250.0) < 10.0

    def test_unknown_operation(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive, _handle_boolean_operation

_handle_create_primitive(shape_type="box", label="A")
_handle_create_primitive(shape_type="box", label="B")
doc.recompute()

r = _handle_boolean_operation(operation="xor", object1="A", object2="B")
results["data"] = {
    "success": r.success,
    "error": r.error,
}
""")
        assert result["ok"]
        d = result["data"]
        assert not d["success"]
        assert "Unknown operation" in d["error"]


class TestTransformObject:
    def test_translate(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive, _handle_transform_object

_handle_create_primitive(shape_type="box", label="Box")
doc.recompute()

r = _handle_transform_object(object_name="Box", translate_x=10, translate_y=20, translate_z=30)
doc.recompute()

obj = doc.getObject("Box")
results["data"] = {
    "success": r.success,
    "x": obj.Placement.Base.x,
    "y": obj.Placement.Base.y,
    "z": obj.Placement.Base.z,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["x"] == 10.0
        assert d["y"] == 20.0
        assert d["z"] == 30.0

    def test_rotate(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive, _handle_transform_object

_handle_create_primitive(shape_type="box", label="Box")
doc.recompute()

r = _handle_transform_object(
    object_name="Box",
    rotate_axis_z=1.0,
    rotate_angle=90.0,
)
doc.recompute()

obj = doc.getObject("Box")
results["data"] = {
    "success": r.success,
    "angle": obj.Placement.Rotation.Angle,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        # Rotation angle should be ~90 degrees (in radians: pi/2 ≈ 1.5708)
        import math
        assert abs(d["angle"] - math.pi / 2) < 0.01
