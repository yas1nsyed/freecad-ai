"""Tests for geometry validation engine."""
import math
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from freecad_ai.extensions.skills import Skill, SkillsRegistry
from freecad_ai.extensions.skill_validator import (
    CheckResult,
    ParamDef,
    ValidationRule,
    compute_pass_rate,
    parse_validation_md,
    run_checks,
    safe_arithmetic,
    validate_skill,
    _resolve_params,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_shape(
    volume: float = 1000.0,
    xlen: float = 10.0,
    ylen: float = 10.0,
    zlen: float = 10.0,
    is_valid: bool = True,
    num_solids: int = 1,
):
    """Create a mock FreeCAD Shape object."""
    bbox = SimpleNamespace(XLength=xlen, YLength=ylen, ZLength=zlen)
    solids = [SimpleNamespace()] * num_solids
    return SimpleNamespace(
        Volume=volume,
        BoundBox=bbox,
        Solids=solids,
        isValid=lambda: is_valid,
    )


def _mock_doc(objects_dict: dict):
    """Create a mock FreeCAD document.

    objects_dict: {label: object} where each object should have Shape, TypeId, etc.
    """
    all_objects = []
    label_map: dict[str, list] = {}
    for label, obj in objects_dict.items():
        if not hasattr(obj, "Label"):
            obj.Label = label
        if not hasattr(obj, "Name"):
            obj.Name = label
        all_objects.append(obj)
        label_map.setdefault(label, []).append(obj)

    def get_by_label(label):
        return label_map.get(label, [])

    return SimpleNamespace(
        Objects=all_objects,
        getObjectsByLabel=get_by_label,
    )


# ---------------------------------------------------------------------------
# TestSafeArithmetic
# ---------------------------------------------------------------------------


class TestSafeArithmetic:
    def test_basic_addition(self):
        assert safe_arithmetic("2 + 3") == 5.0

    def test_subtraction(self):
        assert safe_arithmetic("10 - 4") == 6.0

    def test_multiplication(self):
        assert safe_arithmetic("3 * 4") == 12.0

    def test_division(self):
        assert safe_arithmetic("10 / 4") == 2.5

    def test_power(self):
        assert safe_arithmetic("2 ** 3") == 8.0

    def test_modulo(self):
        assert safe_arithmetic("10 % 3") == 1.0

    def test_parentheses(self):
        assert safe_arithmetic("(2 + 3) * 4") == 20.0

    def test_unary_minus(self):
        assert safe_arithmetic("-5 + 10") == 5.0

    def test_unary_plus(self):
        assert safe_arithmetic("+5") == 5.0

    def test_pi_constant(self):
        assert abs(safe_arithmetic("pi") - math.pi) < 1e-10

    def test_sqrt_function(self):
        assert safe_arithmetic("sqrt(9)") == 3.0

    def test_abs_function(self):
        assert safe_arithmetic("abs(-5)") == 5.0

    def test_min_function(self):
        assert safe_arithmetic("min(3, 7)") == 3.0

    def test_max_function(self):
        assert safe_arithmetic("max(3, 7)") == 7.0

    def test_variables(self):
        assert safe_arithmetic("L * W", {"L": 10, "W": 5}) == 50.0

    def test_complex_expression(self):
        result = safe_arithmetic("L * W * H - 2 * T", {"L": 100, "W": 60, "H": 40, "T": 2})
        assert result == 100 * 60 * 40 - 2 * 2

    def test_reject_import(self):
        with pytest.raises(ValueError):
            safe_arithmetic("__import__('os')")

    def test_reject_attribute_access(self):
        with pytest.raises(ValueError):
            safe_arithmetic("foo.bar", {"foo": 1})

    def test_reject_unknown_function(self):
        with pytest.raises(ValueError):
            safe_arithmetic("open('x')")

    def test_unknown_variable(self):
        with pytest.raises(ValueError, match="Unknown variable"):
            safe_arithmetic("x + 1")

    def test_empty_expression(self):
        with pytest.raises(ValueError, match="Empty expression"):
            safe_arithmetic("")

    def test_division_by_zero(self):
        with pytest.raises(ValueError, match="Division by zero"):
            safe_arithmetic("1 / 0")

    def test_reject_string_literal(self):
        with pytest.raises(ValueError):
            safe_arithmetic("'hello'")


# ---------------------------------------------------------------------------
# TestParseValidationMd
# ---------------------------------------------------------------------------


class TestParseValidationMd:
    def test_parameters_section(self):
        content = """\
## Parameters
L: float
W: float = 60
T: float = 2
lid_type: str = screw
count: int = 4
active: bool = true
"""
        params, rules = parse_validation_md(content)
        assert len(params) == 6
        assert params["L"].type == "float"
        assert params["L"].default is None
        assert params["W"].default == 60.0
        assert params["T"].default == 2.0
        assert params["lid_type"].type == "str"
        assert params["lid_type"].default == "screw"
        assert params["count"].default == 4
        assert params["active"].default is True

    def test_unconditional_rules(self):
        content = """\
## Checks
### Body count
- total_bodies: 2
"""
        params, rules = parse_validation_md(content)
        assert len(rules) == 1
        r = rules[0]
        assert r.target == "_document"
        assert r.check == "total_bodies"
        assert r.expected == "2"
        assert r.condition is None

    def test_object_rules(self):
        content = """\
## Checks
### EnclosureBase
- exists: true
- valid_solid: true
"""
        params, rules = parse_validation_md(content)
        assert len(rules) == 2
        assert rules[0].target == "EnclosureBase"
        assert rules[1].target == "EnclosureBase"

    def test_conditional_rules(self):
        content = """\
## Checks
### ScrewBoss
#### when lid_type == "screw"
- exists: true
- has_holes: 4
"""
        params, rules = parse_validation_md(content)
        assert len(rules) == 2
        assert rules[0].condition == 'lid_type == "screw"'
        assert rules[1].condition == 'lid_type == "screw"'

    def test_h3_resets_condition(self):
        content = """\
## Checks
### ScrewBoss
#### when lid_type == "screw"
- exists: true
### EnclosureBase
- exists: true
"""
        params, rules = parse_validation_md(content)
        assert rules[0].condition == 'lid_type == "screw"'
        assert rules[1].condition is None

    def test_absolute_tolerance(self):
        content = """\
## Checks
### Box
- bbox: L, W, H (tolerance 0.5)
"""
        _, rules = parse_validation_md(content)
        assert rules[0].tolerance == 0.5
        assert rules[0].tolerance_type == "absolute"
        assert rules[0].expected == "L, W, H"

    def test_relative_tolerance(self):
        content = """\
## Checks
### Box
- volume: L * W * H (tolerance 5%)
"""
        _, rules = parse_validation_md(content)
        assert rules[0].tolerance == 5.0
        assert rules[0].tolerance_type == "relative"
        assert rules[0].expected == "L * W * H"

    def test_empty_input(self):
        params, rules = parse_validation_md("")
        assert params == {}
        assert rules == []

    def test_malformed_lines_ignored(self):
        content = """\
## Parameters
not a valid line
L: float
## Checks
this is not a check line
### Box
also not valid
- exists: true
"""
        params, rules = parse_validation_md(content)
        assert len(params) == 1
        assert params["L"].type == "float"
        assert len(rules) == 1
        assert rules[0].check == "exists"


# ---------------------------------------------------------------------------
# TestRunChecks
# ---------------------------------------------------------------------------


class TestRunChecks:
    def test_total_bodies_pass(self):
        body = SimpleNamespace(TypeId="PartDesign::Body", Label="Body", Name="Body")
        doc = _mock_doc({"Body": body})
        rules = [ValidationRule(target="_document", check="total_bodies", expected="1")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_total_bodies_fail(self):
        body = SimpleNamespace(TypeId="PartDesign::Body", Label="Body", Name="Body")
        doc = _mock_doc({"Body": body})
        rules = [ValidationRule(target="_document", check="total_bodies", expected="2")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False

    def test_exists_pass(self):
        obj = SimpleNamespace(Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="exists", expected="true")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_exists_fail(self):
        doc = _mock_doc({})
        rules = [ValidationRule(target="MissingObj", check="exists", expected="true")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False

    def test_bbox_pass(self):
        shape = _mock_shape(xlen=100, ylen=60, zlen=40)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box", TypeId="PartDesign::Body")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="bbox", expected="L, W, H", tolerance=0.5)]
        results = run_checks(doc, {"L": 100, "W": 60, "H": 40}, rules)
        assert results[0].passed is True

    def test_bbox_fail(self):
        shape = _mock_shape(xlen=100, ylen=60, zlen=40)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box", TypeId="PartDesign::Body")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="bbox", expected="50, 50, 50", tolerance=0.5)]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False

    def test_volume_pass(self):
        shape = _mock_shape(volume=24000)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [
            ValidationRule(
                target="Box", check="volume", expected="L * W * H",
                tolerance=5, tolerance_type="relative",
            )
        ]
        results = run_checks(doc, {"L": 100, "W": 60, "H": 4}, rules)
        assert results[0].passed is True

    def test_volume_fail(self):
        shape = _mock_shape(volume=10000)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [
            ValidationRule(
                target="Box", check="volume", expected="24000",
                tolerance=1, tolerance_type="relative",
            )
        ]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False

    def test_solid_count_pass(self):
        shape = _mock_shape(num_solids=1)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="solid_count", expected="1")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_valid_solid_pass(self):
        shape = _mock_shape(is_valid=True, num_solids=1)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="valid_solid", expected="true")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_valid_solid_fail(self):
        shape = _mock_shape(is_valid=False, num_solids=1)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="valid_solid", expected="true")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False

    def test_has_holes_pass(self):
        pocket = SimpleNamespace(TypeId="PartDesign::Pocket", Type="ThroughAll", Label="Hole")
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="Body", Name="Body", Group=[pocket])
        doc = _mock_doc({"Body": obj})
        rules = [ValidationRule(target="Body", check="has_holes", expected="1")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_has_feature_pass(self):
        feat = SimpleNamespace(Label="Fillet")
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="Body", Name="Body", Group=[feat])
        doc = _mock_doc({"Body": obj})
        rules = [ValidationRule(target="Body", check="has_feature", expected="Fillet")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_has_feature_fail(self):
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="Body", Name="Body", Group=[])
        doc = _mock_doc({"Body": obj})
        rules = [ValidationRule(target="Body", check="has_feature", expected="Fillet")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False

    def test_min_children_pass(self):
        children = [SimpleNamespace(Label=f"F{i}") for i in range(5)]
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="Body", Name="Body", Group=children)
        doc = _mock_doc({"Body": obj})
        rules = [ValidationRule(target="Body", check="min_children", expected="3")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is True

    def test_condition_match(self):
        obj = SimpleNamespace(Label="Boss", Name="Boss")
        doc = _mock_doc({"Boss": obj})
        rules = [
            ValidationRule(
                target="Boss", check="exists", expected="true",
                condition='lid_type == "screw"',
            )
        ]
        results = run_checks(doc, {"lid_type": "screw"}, rules)
        assert results[0].passed is True
        assert "skipped" not in results[0].message.lower()

    def test_condition_skip(self):
        doc = _mock_doc({})
        rules = [
            ValidationRule(
                target="Boss", check="exists", expected="true",
                condition='lid_type == "screw"',
            )
        ]
        results = run_checks(doc, {"lid_type": "snap"}, rules)
        assert results[0].passed is True
        assert "skipped" in results[0].message.lower()

    def test_condition_not_equals(self):
        obj = SimpleNamespace(Label="Clip", Name="Clip")
        doc = _mock_doc({"Clip": obj})
        rules = [
            ValidationRule(
                target="Clip", check="exists", expected="true",
                condition='lid_type != "none"',
            )
        ]
        results = run_checks(doc, {"lid_type": "screw"}, rules)
        assert results[0].passed is True
        assert "skipped" not in results[0].message.lower()

    def test_bbox_position_pass(self):
        shape = _mock_shape()
        shape.BoundBox.ZMin = 40.0
        shape.BoundBox.ZMax = 42.0
        obj = SimpleNamespace(Shape=shape, Label="Lid", Name="Lid")
        doc = _mock_doc({"Lid": obj})
        rules = [ValidationRule(
            target="Lid", check="bbox_position", expected="H, H+T",
            tolerance=0.5)]
        results = run_checks(doc, {"H": 40, "T": 2}, rules)
        assert results[0].passed is True

    def test_bbox_position_fail_upside_down(self):
        """Catches an upside-down lid (Z position wrong)."""
        shape = _mock_shape()
        shape.BoundBox.ZMin = 0.0   # lid at Z=0 instead of Z=40
        shape.BoundBox.ZMax = 2.0
        obj = SimpleNamespace(Shape=shape, Label="Lid", Name="Lid")
        doc = _mock_doc({"Lid": obj})
        rules = [ValidationRule(
            target="Lid", check="bbox_position", expected="H, H+T",
            tolerance=0.5)]
        results = run_checks(doc, {"H": 40, "T": 2}, rules)
        assert results[0].passed is False
        assert "0.0" in results[0].message

    def test_section_area_pass(self):
        """Section area check with matching area."""
        import sys
        mock_freecad = SimpleNamespace(
            Vector=lambda x, y, z: (x, y, z))
        # (L-2*T-0.4)*(W-2*T-0.4) = (100-4-0.4)*(80-4-0.4) = 95.6*75.6 = 7227.36
        mock_face = SimpleNamespace(Area=7200.0)  # within 10% tolerance
        mock_part = SimpleNamespace(
            Face=lambda wires: mock_face)
        sys.modules["FreeCAD"] = mock_freecad
        sys.modules["Part"] = mock_part
        try:
            shape = _mock_shape()
            wire = SimpleNamespace()
            shape.slice = lambda direction, offset: [wire]
            obj = SimpleNamespace(Shape=shape, Label="Lid", Name="Lid")
            doc = _mock_doc({"Lid": obj})
            rules = [ValidationRule(
                target="Lid", check="section_area",
                expected="Z, H-1, (L-2*T-0.4)*(W-2*T-0.4)",
                tolerance=10.0, tolerance_type="relative")]
            results = run_checks(doc, {"H": 40, "L": 100, "W": 80, "T": 2}, rules)
            assert results[0].passed is True
        finally:
            sys.modules.pop("FreeCAD", None)
            sys.modules.pop("Part", None)

    def test_section_area_fail_no_material(self):
        """Section area zero when lid is flipped (no material at expected Z)."""
        import sys
        mock_freecad = SimpleNamespace(
            Vector=lambda x, y, z: (x, y, z))
        mock_part = SimpleNamespace(Face=lambda wires: None)
        sys.modules["FreeCAD"] = mock_freecad
        sys.modules["Part"] = mock_part
        try:
            shape = _mock_shape()
            shape.slice = lambda direction, offset: []  # no wires = no material
            obj = SimpleNamespace(Shape=shape, Label="Lid", Name="Lid")
            doc = _mock_doc({"Lid": obj})
            rules = [ValidationRule(
                target="Lid", check="section_area",
                expected="Z, H-1, (L-2*T-0.4)*(W-2*T-0.4)",
                tolerance=10.0, tolerance_type="relative")]
            results = run_checks(doc, {"H": 40, "L": 100, "W": 80, "T": 2}, rules)
            assert results[0].passed is False
            assert "0.0" in results[0].message
        finally:
            sys.modules.pop("FreeCAD", None)
            sys.modules.pop("Part", None)

    def test_section_area_bad_axis(self):
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(
            target="Box", check="section_area",
            expected="W, 10, 100")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False
        assert "axis" in results[0].message.lower()

    def test_unknown_check_type(self):
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        rules = [ValidationRule(target="Box", check="unknown_check", expected="42")]
        results = run_checks(doc, {}, rules)
        assert results[0].passed is False
        assert "Unknown check type" in results[0].message


# ---------------------------------------------------------------------------
# TestValidateSkill
# ---------------------------------------------------------------------------


class TestValidateSkill:
    def test_full_flow(self):
        validation_md = """\
## Parameters
L: float = 100
W: float = 60
H: float = 40

## Checks
### Body count
- total_bodies: 1

### EnclosureBase
- exists: true
- valid_solid: true
- bbox: L, W, H (tolerance 0.5)
"""
        shape = _mock_shape(xlen=100, ylen=60, zlen=40, is_valid=True, num_solids=1)
        body = SimpleNamespace(
            Shape=shape, Label="EnclosureBase", Name="EnclosureBase",
            TypeId="PartDesign::Body",
        )
        doc = _mock_doc({"EnclosureBase": body})

        results = validate_skill(doc, {}, validation_md)
        assert len(results) == 4
        assert all(r.passed for r in results)

    def test_pass_rate(self):
        results = [
            CheckResult("A", "exists", True, True, True, "ok"),
            CheckResult("B", "exists", False, True, False, "fail"),
            CheckResult("C", "exists", True, True, True, "ok"),
        ]
        assert compute_pass_rate(results) == pytest.approx(2 / 3)

    def test_pass_rate_empty(self):
        assert compute_pass_rate([]) == 1.0

    def test_malformed_validation_md(self):
        """Malformed content produces no rules -- validate returns empty list."""
        shape = _mock_shape()
        obj = SimpleNamespace(Shape=shape, Label="X", Name="X", TypeId="PartDesign::Body")
        doc = _mock_doc({"X": obj})
        results = validate_skill(doc, {}, "this is not valid markdown")
        assert results == []

    def test_defaults_applied(self):
        validation_md = """\
## Parameters
T: float = 2

## Checks
### Box
- bbox: T, T, T (tolerance 0.1)
"""
        shape = _mock_shape(xlen=2, ylen=2, zlen=2)
        obj = SimpleNamespace(Shape=shape, Label="Box", Name="Box")
        doc = _mock_doc({"Box": obj})
        # Don't pass T -- it should use the default
        results = validate_skill(doc, {}, validation_md)
        assert len(results) == 1
        assert results[0].passed is True


class TestSkillValidationDiscovery:
    def test_skill_dataclass_accepts_validation_path(self):
        skill = Skill(name="test", validation_path="/tmp/VALIDATION.md")
        assert skill.validation_path == "/tmp/VALIDATION.md"

    def test_skill_dataclass_default_validation_path(self):
        skill = Skill(name="test")
        assert skill.validation_path == ""

    def test_registry_finds_validation_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "myskill")
            os.makedirs(skill_dir)
            # Create SKILL.md
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("# My Skill\nA test skill.")
            # Create VALIDATION.md
            val_path = os.path.join(skill_dir, "VALIDATION.md")
            with open(val_path, "w") as f:
                f.write("## Checks\n### Box\n- exists: true\n")

            registry = SkillsRegistry.__new__(SkillsRegistry)
            registry._skills = {}
            registry._scan_skills_dir(tmpdir)

            skill = registry.get_skill("myskill")
            assert skill is not None
            assert skill.validation_path == val_path

    def test_registry_no_validation_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "myskill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("# My Skill\nA test skill.")

            registry = SkillsRegistry.__new__(SkillsRegistry)
            registry._skills = {}
            registry._scan_skills_dir(tmpdir)

            skill = registry.get_skill("myskill")
            assert skill is not None
            assert skill.validation_path == ""


class TestResolveParams:
    def test_fills_defaults(self):
        defs = {"L": ParamDef("L", "float", 100.0), "W": ParamDef("W", "float", 60.0)}
        result = _resolve_params({"L": 200}, defs)
        assert result["L"] == 200
        assert result["W"] == 60.0

    def test_no_default_not_added(self):
        defs = {"L": ParamDef("L", "float", None)}
        result = _resolve_params({}, defs)
        assert "L" not in result
