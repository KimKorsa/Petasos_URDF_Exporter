from __future__ import annotations

import math
from typing import Any

from URDF_Exporter.standalone.occ_loader import load_ocp


MAX_SNAP_FEATURES = 12000


def _xyz(value) -> list[float]:
    return [float(value.X()), float(value.Y()), float(value.Z())]


def _unit_xyz(value) -> list[float] | None:
    result = _xyz(value)
    length = math.sqrt(sum(component * component for component in result))
    if length <= 1e-12:
        return None
    return [component / length for component in result]


def _feature_key(feature: dict[str, Any]) -> tuple:
    position = feature.get("position") or [0.0, 0.0, 0.0]
    normal = feature.get("normal") or [0.0, 0.0, 0.0]
    radius = float(feature.get("radius") or 0.0)
    return (
        str(feature.get("type") or ""),
        *(round(float(value), 5) for value in position),
        *(round(float(value), 5) for value in normal),
        round(radius, 5),
    )


def _append_unique(
    target: list[dict[str, Any]],
    seen: set[tuple],
    feature: dict[str, Any],
) -> None:
    key = _feature_key(feature)
    if key in seen:
        return
    seen.add(key)
    feature["source"] = "opencascade"
    target.append(feature)


def _edge_tangent(adaptor, parameter: float) -> list[float] | None:
    first = float(adaptor.FirstParameter())
    last = float(adaptor.LastParameter())
    span = abs(last - first)
    if not math.isfinite(span) or span <= 1e-12:
        return None
    delta = max(span * 1e-5, 1e-7)
    low = max(min(first, last), parameter - delta)
    high = min(max(first, last), parameter + delta)
    if high - low <= 1e-12:
        return None
    before = adaptor.Value(low)
    after = adaptor.Value(high)
    vector = [
        float(after.X() - before.X()),
        float(after.Y() - before.Y()),
        float(after.Z() - before.Z()),
    ]
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-12:
        return None
    return [component / length for component in vector]


def extract_occ_snap_features(shape, max_features: int = MAX_SNAP_FEATURES) -> list[dict[str, Any]]:
    """Extract exact CAD snap entities from an OpenCascade shape.

    Coordinates remain in the CAD shape's native local millimetre frame, which
    is also the frame used by the STL preview generated from the same shape.
    """

    load_ocp()
    from OCP import (
        BRep,
        BRepAdaptor,
        BRepGProp,
        GeomAbs,
        GProp,
        TopAbs,
        TopExp,
        TopoDS,
    )

    priority: dict[str, list[dict[str, Any]]] = {
        "circle": [],
        "axis": [],
        "face": [],
        "edge": [],
        "vertex": [],
    }
    seen: set[tuple] = set()

    explorer = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_EDGE)
    edge_index = 0
    while explorer.More():
        edge = TopoDS.TopoDS.Edge(explorer.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Curve(edge)
        first = float(adaptor.FirstParameter())
        last = float(adaptor.LastParameter())
        middle = (first + last) / 2.0
        midpoint = adaptor.Value(middle)
        tangent = _edge_tangent(adaptor, middle)
        curve_type = adaptor.GetType()
        edge_id = f"edge_{edge_index}"
        edge_index += 1

        edge_feature: dict[str, Any] = {
            "type": "edge_midpoint",
            "position": _xyz(midpoint),
            "entity_id": edge_id,
        }
        if tangent:
            edge_feature["tangent"] = tangent
        _append_unique(priority["edge"], seen, edge_feature)

        if curve_type == GeomAbs.GeomAbs_Circle:
            circle = adaptor.Circle()
            axis = circle.Axis().Direction()
            x_axis = circle.XAxis().Direction()
            angular_span = abs(last - first)
            feature_type = (
                "circle_center"
                if angular_span >= (math.pi * 2.0 - 1e-5)
                else "arc_center"
            )
            _append_unique(
                priority["circle"],
                seen,
                {
                    "type": feature_type,
                    "position": _xyz(circle.Location()),
                    "normal": _unit_xyz(axis),
                    "tangent": _unit_xyz(x_axis),
                    "radius": float(circle.Radius()),
                    "angular_span": angular_span,
                    "entity_id": edge_id,
                },
            )
        explorer.Next()

    explorer = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_FACE)
    face_index = 0
    while explorer.More():
        face = TopoDS.TopoDS.Face(explorer.Current())
        adaptor = BRepAdaptor.BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()
        props = GProp.GProp_GProps()
        BRepGProp.BRepGProp.SurfaceProperties_s(face, props)
        center = props.CentreOfMass()
        reversed_face = face.Orientation() == TopAbs.TopAbs_REVERSED
        face_id = f"face_{face_index}"
        face_index += 1

        if surface_type == GeomAbs.GeomAbs_Plane:
            plane = adaptor.Plane()
            normal = _unit_xyz(plane.Axis().Direction())
            tangent = _unit_xyz(plane.XAxis().Direction())
            if normal and reversed_face:
                normal = [-value for value in normal]
            _append_unique(
                priority["face"],
                seen,
                {
                    "type": "planar_face_center",
                    "position": _xyz(center),
                    "normal": normal,
                    "tangent": tangent,
                    "area": float(props.Mass()),
                    "entity_id": face_id,
                },
            )
        elif surface_type == GeomAbs.GeomAbs_Cylinder:
            cylinder = adaptor.Cylinder()
            location = cylinder.Location()
            direction = _unit_xyz(cylinder.Axis().Direction())
            tangent = _unit_xyz(cylinder.XAxis().Direction())
            if direction:
                offset = [
                    float(center.X() - location.X()),
                    float(center.Y() - location.Y()),
                    float(center.Z() - location.Z()),
                ]
                along_axis = sum(
                    offset[index] * direction[index] for index in range(3)
                )
                axis_center = [
                    float(location.X()) + along_axis * direction[0],
                    float(location.Y()) + along_axis * direction[1],
                    float(location.Z()) + along_axis * direction[2],
                ]
                _append_unique(
                    priority["axis"],
                    seen,
                    {
                        "type": "cylinder_axis",
                        "position": axis_center,
                        "normal": direction,
                        "tangent": tangent,
                        "radius": float(cylinder.Radius()),
                        "area": float(props.Mass()),
                        "entity_id": face_id,
                    },
                )
        explorer.Next()

    explorer = TopExp.TopExp_Explorer(shape, TopAbs.TopAbs_VERTEX)
    vertex_index = 0
    while explorer.More():
        vertex = TopoDS.TopoDS.Vertex(explorer.Current())
        point = BRep.BRep_Tool.Pnt_s(vertex)
        _append_unique(
            priority["vertex"],
            seen,
            {
                "type": "vertex",
                "position": _xyz(point),
                "entity_id": f"vertex_{vertex_index}",
            },
        )
        vertex_index += 1
        explorer.Next()

    ordered: list[dict[str, Any]] = []
    for group in ("circle", "axis", "face", "edge", "vertex"):
        remaining = max_features - len(ordered)
        if remaining <= 0:
            break
        ordered.extend(priority[group][:remaining])
    return ordered
