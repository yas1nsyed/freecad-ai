"""Integration test: full enclosure construction workflow.

Tests the complete 9-tool sequence:
  1. create_body (base)
  2. create_sketch (outer rectangle)
  3. pad_sketch (solid block)
  4. create_sketch (inner pocket, offset=H)
  5. pocket_sketch (hollow the box)
  6. create_enclosure_lid
  7. transform_object (position lid)
  8. create_inner_ridge
  9. create_snap_tabs
"""

import pytest

pytestmark = pytest.mark.integration


class TestEnclosureWorkflow:
    def test_full_enclosure(self, run_freecad_script):
        result = run_freecad_script("""
from freecad_ai.tools.freecad_tools import (
    _handle_create_body, _handle_create_sketch, _handle_pad_sketch,
    _handle_pocket_sketch, _handle_create_enclosure_lid,
    _handle_transform_object, _handle_create_inner_ridge,
    _handle_create_snap_tabs,
)

L, W, H, T = 80, 60, 30, 2

# 1. Create base body
base_r = _handle_create_body(label="EnclosureBase")
doc.recompute()
base_name = base_r.data["name"]

# 2. Outer sketch
outer_r = _handle_create_sketch(
    body_name=base_name,
    geometries=[{"type": "rectangle", "x": 0, "y": 0, "width": L, "height": W}],
)
doc.recompute()

# 3. Pad to full height
_handle_pad_sketch(sketch_name=outer_r.data["name"], length=H)
doc.recompute()

base = doc.getObject(base_name)
vol_solid = base.Shape.Volume

# 4. Inner sketch at top
inner_r = _handle_create_sketch(
    body_name=base_name,
    plane="XY",
    offset=float(H),
    geometries=[{"type": "rectangle", "x": T, "y": T, "width": L-2*T, "height": W-2*T}],
)
doc.recompute()

# 5. Pocket to hollow
pocket_r = _handle_pocket_sketch(
    sketch_name=inner_r.data["name"],
    length=float(H - T),
)
doc.recompute()

vol_hollow = base.Shape.Volume

# 6. Create lid
lid_r = _handle_create_enclosure_lid(
    length=L, width=W, wall_thickness=T,
    clearance=1.0, lip_height=3.0,
)
doc.recompute()

lid_name = lid_r.data["name"]
lid = doc.getObject(lid_name)

# 7. Position lid
_handle_transform_object(
    object_name=lid_name,
    translate_z=float(H - 3),  # H - lip_height
)
doc.recompute()

# 8. Inner ridge on base
ridge_r = _handle_create_inner_ridge(
    body_name=base_name,
    length=L, width=W,
    wall_thickness=T,
    z_position=float(H - 2),
)
doc.recompute()

# 9. Snap tabs on lid
tabs_r = _handle_create_snap_tabs(
    body_name=lid_name,
    length=L, width=W,
    wall_thickness=T,
    clearance=1.0,
    lip_height=3.0,
)
doc.recompute()

# Verify all objects exist
obj_names = [o.Name for o in doc.Objects]
obj_labels = [o.Label for o in doc.Objects]

results["data"] = {
    "base_exists": base_name in obj_names,
    "lid_exists": lid_name in obj_names or lid_name in obj_labels,
    "vol_solid": vol_solid,
    "vol_hollow": vol_hollow,
    "is_hollow": vol_hollow < vol_solid * 0.5,
    "pocket_success": pocket_r.success,
    "lid_success": lid_r.success,
    "ridge_success": ridge_r.success,
    "tabs_success": tabs_r.success,
    "lid_z": lid.Placement.Base.z,
    "total_objects": len(doc.Objects),
    "tab_label_exists": any("SnapTab" in l for l in obj_labels),
    "ridge_label_exists": any("Ridge" in l for l in obj_labels),
}
""", timeout=120)
        assert result["ok"], f"Script error: {result.get('error', '')}"
        d = result["data"]

        # All steps succeeded
        assert d["pocket_success"], "Pocket should succeed"
        assert d["lid_success"], "Lid creation should succeed"
        assert d["ridge_success"], "Ridge creation should succeed"
        assert d["tabs_success"], "Snap tab creation should succeed"

        # Objects exist
        assert d["base_exists"], "Base body should exist"
        assert d["lid_exists"], "Lid body should exist"
        assert d["tab_label_exists"], "SnapTab object should exist"
        assert d["ridge_label_exists"], "Ridge object should exist"

        # Base is properly hollowed
        assert d["is_hollow"], "Base should be hollow (vol < 50% of solid)"

        # Lid is positioned correctly
        assert abs(d["lid_z"] - 27.0) < 0.1, "Lid should be at z=H-lip_height=27"

        # Reasonable object count (body, sketches, features, lid, tabs)
        assert d["total_objects"] >= 10, "Should have many objects in the document"
