"""Tests for the list_edges tool and _classify_edge helper."""

import pytest
from unittest.mock import MagicMock

from freecad_ai.tools.freecad_tools import (
    LIST_EDGES, _classify_edge, _resolve_edge_refs, _resolve_face_refs,
)


class TestListEdgesDefinition:
    """Verify the ToolDefinition is properly configured."""

    def test_name(self):
        assert LIST_EDGES.name == "list_edges"

    def test_category(self):
        assert LIST_EDGES.category == "query"

    def test_has_object_name_param(self):
        names = [p.name for p in LIST_EDGES.parameters]
        assert "object_name" in names

    def test_in_all_tools(self):
        from freecad_ai.tools.freecad_tools import ALL_TOOLS
        assert LIST_EDGES in ALL_TOOLS


class TestClassifyEdge:
    """Test the _classify_edge helper for various edge orientations."""

    def _make_point(self, x, y, z):
        p = MagicMock()
        p.x, p.y, p.z = x, y, z
        return p

    def _make_line_edge(self, p1, p2, midpoint):
        """Create a mock straight edge."""
        edge = MagicMock()
        edge.Curve.__class__ = type("Line", (), {})
        edge.Curve.__class__.__name__ = "Line"
        v1 = MagicMock()
        v1.Point = self._make_point(*p1)
        v2 = MagicMock()
        v2.Point = self._make_point(*p2)
        edge.Vertexes = [v1, v2]
        edge.CenterOfMass = self._make_point(*midpoint)
        edge.Length = sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
        return edge

    def _make_bbox(self, xmin=0, xmax=100, ymin=0, ymax=60, zmin=0, zmax=40):
        bb = MagicMock()
        bb.XMin, bb.XMax = xmin, xmax
        bb.YMin, bb.YMax = ymin, ymax
        bb.ZMin, bb.ZMax = zmin, zmax
        return bb

    def test_front_left_vertical(self):
        edge = self._make_line_edge((0, 0, 0), (0, 0, 40), (0, 0, 20))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "front-left vertical"

    def test_top_front_horizontal_x(self):
        edge = self._make_line_edge((0, 0, 40), (100, 0, 40), (50, 0, 40))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "top-front horizontal-X"

    def test_top_back_horizontal_x(self):
        edge = self._make_line_edge((0, 60, 40), (100, 60, 40), (50, 60, 40))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "top-back horizontal-X"

    def test_bottom_left_horizontal_y(self):
        edge = self._make_line_edge((0, 0, 0), (0, 60, 0), (0, 30, 0))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "bottom-left horizontal-Y"

    def test_top_right_horizontal_y(self):
        edge = self._make_line_edge((100, 0, 40), (100, 60, 40), (100, 30, 40))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "top-right horizontal-Y"

    def test_back_right_vertical(self):
        edge = self._make_line_edge((100, 60, 0), (100, 60, 40), (100, 60, 20))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "back-right vertical"

    def test_interior_edge(self):
        """An edge not at any bounding box boundary."""
        edge = self._make_line_edge((50, 30, 0), (50, 30, 40), (50, 30, 20))
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "interior vertical"

    def test_circular_edge(self):
        edge = MagicMock()
        edge.Curve.__class__ = type("Circle", (), {})
        edge.Curve.__class__.__name__ = "Circle"
        edge.Curve.Radius = 8.0
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "circular (R=8.0)"

    def test_arc_edge(self):
        edge = MagicMock()
        edge.Curve.__class__ = type("ArcOfCircle", (), {})
        edge.Curve.__class__.__name__ = "ArcOfCircle"
        edge.Curve.Radius = 3.0
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "circular (R=3.0)"

    def test_spline_edge(self):
        edge = MagicMock()
        edge.Curve.__class__ = type("BSplineCurve", (), {})
        edge.Curve.__class__.__name__ = "BSplineCurve"
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "spline"

    def test_elliptical_edge(self):
        edge = MagicMock()
        edge.Curve.__class__ = type("Ellipse", (), {})
        edge.Curve.__class__.__name__ = "Ellipse"
        bbox = self._make_bbox()
        assert _classify_edge(edge, bbox) == "elliptical"

    def test_diagonal_edge(self):
        edge = self._make_line_edge((0, 0, 0), (100, 60, 40), (50, 30, 20))
        bbox = self._make_bbox()
        result = _classify_edge(edge, bbox)
        assert "diagonal" in result


class _MockShapeHelper:
    """Shared helpers for creating mock shapes with edges and faces."""

    @staticmethod
    def _make_point(x, y, z):
        p = MagicMock()
        p.x, p.y, p.z = x, y, z
        return p

    @staticmethod
    def _make_bbox(xmin=0, xmax=50, ymin=0, ymax=30, zmin=0, zmax=20):
        bb = MagicMock()
        bb.XMin, bb.XMax = xmin, xmax
        bb.YMin, bb.YMax = ymin, ymax
        bb.ZMin, bb.ZMax = zmin, zmax
        return bb

    @classmethod
    def _make_line_edge(cls, p1, p2, midpoint):
        edge = MagicMock()
        edge.Curve.__class__ = type("Line", (), {})
        edge.Curve.__class__.__name__ = "Line"
        v1 = MagicMock()
        v1.Point = cls._make_point(*p1)
        v2 = MagicMock()
        v2.Point = cls._make_point(*p2)
        edge.Vertexes = [v1, v2]
        edge.CenterOfMass = cls._make_point(*midpoint)
        edge.Length = sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
        return edge

    @classmethod
    def _make_box_shape(cls):
        """Create a mock shape resembling a 50x30x20 box with 12 edges."""
        bbox = cls._make_bbox()
        edges = [
            # 4 vertical edges
            cls._make_line_edge((0, 0, 0), (0, 0, 20), (0, 0, 10)),       # front-left vertical
            cls._make_line_edge((50, 0, 0), (50, 0, 20), (50, 0, 10)),    # front-right vertical
            cls._make_line_edge((0, 30, 0), (0, 30, 20), (0, 30, 10)),    # back-left vertical
            cls._make_line_edge((50, 30, 0), (50, 30, 20), (50, 30, 10)), # back-right vertical
            # 4 top horizontal edges
            cls._make_line_edge((0, 0, 20), (50, 0, 20), (25, 0, 20)),    # top-front horizontal-X
            cls._make_line_edge((0, 30, 20), (50, 30, 20), (25, 30, 20)), # top-back horizontal-X
            cls._make_line_edge((0, 0, 20), (0, 30, 20), (0, 15, 20)),    # top-left horizontal-Y
            cls._make_line_edge((50, 0, 20), (50, 30, 20), (50, 15, 20)), # top-right horizontal-Y
            # 4 bottom horizontal edges
            cls._make_line_edge((0, 0, 0), (50, 0, 0), (25, 0, 0)),       # bottom-front horizontal-X
            cls._make_line_edge((0, 30, 0), (50, 30, 0), (25, 30, 0)),    # bottom-back horizontal-X
            cls._make_line_edge((0, 0, 0), (0, 30, 0), (0, 15, 0)),       # bottom-left horizontal-Y
            cls._make_line_edge((50, 0, 0), (50, 30, 0), (50, 15, 0)),    # bottom-right horizontal-Y
        ]
        shape = MagicMock()
        shape.Edges = edges
        shape.BoundBox = bbox
        return shape


class TestResolveEdgeRefs(_MockShapeHelper):
    """Tests for _resolve_edge_refs filter keyword resolution."""

    def test_explicit_refs_passed_through(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["Edge1", "Edge3"])
        assert result == ["Edge1", "Edge3"]

    def test_all_returns_all_edges(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["all"])
        assert len(result) == 12
        assert result[0] == "Edge1"
        assert result[-1] == "Edge12"

    def test_vertical_filter(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["vertical"])
        assert len(result) == 4
        # First 4 edges are vertical in our mock
        assert result == ["Edge1", "Edge2", "Edge3", "Edge4"]

    def test_top_filter(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["top"])
        assert len(result) == 4
        # Edges 5-8 are top edges
        assert result == ["Edge5", "Edge6", "Edge7", "Edge8"]

    def test_bottom_filter(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["bottom"])
        assert len(result) == 4

    def test_combined_filters_union(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["top", "vertical"])
        # Should include all vertical + all top = 8 edges
        assert len(result) == 8

    def test_mixed_explicit_and_filter(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["Edge1", "top"])
        assert "Edge1" in result
        assert len(result) >= 5  # Edge1 + 4 top edges (Edge1 might overlap)

    def test_empty_filter_result(self):
        shape = self._make_box_shape()
        result = _resolve_edge_refs(shape, ["circular"])
        assert result == []  # No circular edges in a box
