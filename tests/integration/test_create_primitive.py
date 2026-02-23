"""Integration tests for create_primitive tool."""

import pytest

pytestmark = pytest.mark.integration


class TestCreatePrimitive:
    def test_create_box(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive

r = _handle_create_primitive(shape_type="box", length=20, width=15, height=10)
doc.recompute()
obj = doc.getObject("Box")
results["data"] = {
    "success": r.success,
    "output": r.output,
    "volume": obj.Shape.Volume,
    "type_id": obj.TypeId,
    "length": obj.Length.Value,
    "width": obj.Width.Value,
    "height": obj.Height.Value,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["type_id"] == "Part::Box"
        assert abs(d["volume"] - 3000.0) < 1.0  # 20*15*10
        assert d["length"] == 20.0

    def test_create_cylinder(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive
import math

r = _handle_create_primitive(shape_type="cylinder", radius=5, height=20)
doc.recompute()
obj = doc.getObject("Cylinder")
expected_vol = math.pi * 5**2 * 20
results["data"] = {
    "success": r.success,
    "volume": obj.Shape.Volume,
    "expected": expected_vol,
    "type_id": obj.TypeId,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert abs(d["volume"] - d["expected"]) < 1.0

    def test_create_sphere(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive
import math

r = _handle_create_primitive(shape_type="sphere", radius=10)
doc.recompute()
obj = doc.getObject("Sphere")
expected_vol = (4/3) * math.pi * 10**3
results["data"] = {
    "success": r.success,
    "volume": obj.Shape.Volume,
    "expected": expected_vol,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert abs(d["volume"] - d["expected"]) < 10.0

    def test_create_cone(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive

r = _handle_create_primitive(shape_type="cone", radius=10, radius2=3, height=15)
doc.recompute()
obj = doc.getObject("Cone")
results["data"] = {
    "success": r.success,
    "volume": obj.Shape.Volume,
    "type_id": obj.TypeId,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["volume"] > 0

    def test_create_torus(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive

r = _handle_create_primitive(shape_type="torus", radius=10, radius2=3)
doc.recompute()
obj = doc.getObject("Torus")
results["data"] = {
    "success": r.success,
    "volume": obj.Shape.Volume,
    "type_id": obj.TypeId,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["success"]
        assert d["volume"] > 0

    def test_create_with_position(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive

r = _handle_create_primitive(shape_type="box", x=10, y=20, z=30)
doc.recompute()
obj = doc.getObject("Box")
results["data"] = {
    "x": obj.Placement.Base.x,
    "y": obj.Placement.Base.y,
    "z": obj.Placement.Base.z,
}
""")
        assert result["ok"]
        d = result["data"]
        assert d["x"] == 10.0
        assert d["y"] == 20.0
        assert d["z"] == 30.0

    def test_unknown_shape_type(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import _handle_create_primitive

r = _handle_create_primitive(shape_type="hexagon")
results["data"] = {
    "success": r.success,
    "error": r.error,
}
""")
        assert result["ok"]
        d = result["data"]
        assert not d["success"]
        assert "Unknown shape type" in d["error"]
