"""
Tests for document context property extraction helpers.
Specifically, pad and rotation features
"""

from types import SimpleNamespace
from freecad_ai.core.context import _get_key_properties

class TestGetKeyProperties:
    # Pad with TwoLengths should include type, primary/secondary lengths, and reversed flag.
    def test_pad_two_lengths_gives_length_length2_and_reversed(self):
        obj = SimpleNamespace(
            TypeId="PartDesign::Pad",
            Type="TwoLengths",
            Length="10 mm",
            Length2="3 mm",
            Reversed=True,
        )

        props = _get_key_properties(obj)

        assert "Type: TwoLengths" in props
        assert "Length: 10 mm" in props
        assert "Length2: 3 mm" in props
        assert "Reversed: true" in props

    # Pocket with non-TwoLengths should not include Length2 or reversed flag when Reversed is False.
    def test_pocket_dimension_omits_length2_and_reversed(self):
        obj = SimpleNamespace(
            TypeId="PartDesign::Pocket",
            Type="Dimension",
            Length="7 mm",
            Reversed=False,
            Length2="99 mm",
        )

        props = _get_key_properties(obj)

        assert "Type: Dimension" in props
        assert "Length: 7 mm" in props
        assert "Length2: 99 mm" not in props
        assert "Reversed: true" not in props

    # Revolution with TwoAngles should include type, both angles, reference axis, and reversed flag.
    def test_revolution_two_angles_gives_angle2_axis_and_reversed(self):
        obj = SimpleNamespace(
            TypeId="PartDesign::Revolution",
            Type="TwoAngles",
            Angle="180 deg",
            Angle2="30 deg",
            ReferenceAxis="(Sketch.Axis, V_Axis)",
            Reversed=True,
        )

        props = _get_key_properties(obj)

        assert "Type: TwoAngles" in props
        assert "Angle: 180 deg" in props
        assert "Angle2: 30 deg" in props
        assert "ReferenceAxis: (Sketch.Axis, V_Axis)" in props
        assert "Reversed: true" in props

    # Revolution with non-TwoAngles should not include Angle2 and should omit reversed when False.
    def test_revolution_angle_omits_angle2_and_reversed(self):
        obj = SimpleNamespace(
            TypeId="PartDesign::Revolution",
            Type="Angle",
            Angle="270 deg",
            Angle2="40 deg",
            Reversed=False,
        )

        props = _get_key_properties(obj)

        assert "Type: Angle" in props
        assert "Angle: 270 deg" in props
        assert "Angle2: 40 deg" not in props
        assert "Reversed: true" not in props
