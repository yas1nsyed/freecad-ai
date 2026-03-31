"""Tests for the list_faces tool and _classify_face helper."""

import sys
import pytest
from unittest.mock import MagicMock, patch

from freecad_ai.tools.freecad_tools import LIST_FACES, _classify_face


class TestListFacesDefinition:
    """Verify the ToolDefinition is properly configured."""

    def test_name(self):
        assert LIST_FACES.name == "list_faces"

    def test_category(self):
        assert LIST_FACES.category == "query"

    def test_has_object_name_param(self):
        names = [p.name for p in LIST_FACES.parameters]
        assert "object_name" in names

    def test_in_all_tools(self):
        from freecad_ai.tools.freecad_tools import ALL_TOOLS
        assert LIST_FACES in ALL_TOOLS


class TestClassifyFace:
    """Test the _classify_face helper for various face orientations."""

    def _make_planar_face(self, normal, center):
        """Create a mock planar face with given normal and center."""
        face = MagicMock()
        face.Surface.__class__ = type("Plane", (), {})
        face.Surface.__class__.__name__ = "Plane"
        n = MagicMock()
        n.x, n.y, n.z = normal
        face.normalAt = MagicMock(return_value=n)
        c = MagicMock()
        c.x, c.y, c.z = center
        face.CenterOfMass = c
        return face

    def _make_bbox(self, xmin=0, xmax=100, ymin=0, ymax=60, zmin=0, zmax=40):
        """Create a mock bounding box."""
        bb = MagicMock()
        bb.XMin, bb.XMax = xmin, xmax
        bb.YMin, bb.YMax = ymin, ymax
        bb.ZMin, bb.ZMax = zmin, zmax
        return bb

    def test_top_face(self):
        face = self._make_planar_face(normal=(0, 0, 1), center=(50, 30, 40))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "top"

    def test_bottom_face(self):
        face = self._make_planar_face(normal=(0, 0, -1), center=(50, 30, 0))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "bottom"

    def test_front_face(self):
        face = self._make_planar_face(normal=(0, -1, 0), center=(50, 0, 20))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "front"

    def test_back_face(self):
        face = self._make_planar_face(normal=(0, 1, 0), center=(50, 60, 20))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "back"

    def test_left_face(self):
        face = self._make_planar_face(normal=(-1, 0, 0), center=(0, 30, 20))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "left"

    def test_right_face(self):
        face = self._make_planar_face(normal=(1, 0, 0), center=(100, 30, 20))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "right"

    def test_interior_horizontal_face(self):
        """A horizontal face NOT at the bounding box boundary."""
        face = self._make_planar_face(normal=(0, 0, 1), center=(50, 30, 20))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "horizontal"

    def test_interior_side_face(self):
        """A side face NOT at the bounding box boundary."""
        face = self._make_planar_face(normal=(1, 0, 0), center=(50, 30, 20))
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "side"

    def test_angled_face(self):
        """A face with a non-axis-aligned normal."""
        face = self._make_planar_face(normal=(0.577, 0.577, 0.577), center=(50, 30, 20))
        bbox = self._make_bbox()
        # All components equal, x is picked first but abs values are same
        result = _classify_face(face, bbox)
        assert result in ("angled", "side")

    def test_cylindrical_face(self):
        face = MagicMock()
        face.Surface.__class__ = type("Cylinder", (), {})
        face.Surface.__class__.__name__ = "Cylinder"
        face.Surface.Radius = 5.0
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "cylindrical (R=5.0)"

    def test_spherical_face(self):
        face = MagicMock()
        face.Surface.__class__ = type("Sphere", (), {})
        face.Surface.__class__.__name__ = "Sphere"
        face.Surface.Radius = 10.0
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "spherical (R=10.0)"

    def test_conical_face(self):
        face = MagicMock()
        face.Surface.__class__ = type("Cone", (), {})
        face.Surface.__class__.__name__ = "Cone"
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "conical"

    def test_toroidal_face(self):
        face = MagicMock()
        face.Surface.__class__ = type("Toroid", (), {})
        face.Surface.__class__.__name__ = "Toroid"
        bbox = self._make_bbox()
        assert _classify_face(face, bbox) == "toroidal"
