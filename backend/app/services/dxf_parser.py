"""DXF file parsing service using ezdxf."""
import ezdxf
import math
from pathlib import Path
from typing import Optional


def parse_dxf_file(file_path: str) -> dict:
    """Parse a DXF file and extract entity data for frontend rendering."""
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    entities = []
    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')

    layer_counts: dict[str, int] = {}

    for entity in msp:
        parsed = _parse_entity(entity)
        if parsed:
            entities.append(parsed)
            layer = parsed.get("layer", "0")
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
            _update_bounds(parsed, locals())

    layers = []
    for layer_def in doc.layers:
        layers.append({
            "name": layer_def.dxf.name,
            "color": layer_def.color,
            "entity_count": layer_counts.get(layer_def.dxf.name, 0),
        })

    if min_x == float('inf'):
        min_x = min_y = 0
        max_x = max_y = 1000

    return {
        "filename": Path(file_path).name,
        "layers": layers,
        "bounds": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "entity_count": len(entities),
        "entities_json": entities,
    }


def _update_bounds(parsed: dict, scope: dict):
    """Update bounding box from parsed entity."""
    pts = []
    etype = parsed.get("type", "")
    if etype == "LINE":
        pts = [parsed.get("start", {}), parsed.get("end", {})]
    elif etype == "CIRCLE":
        cx, cy = parsed.get("center", {}).get("x", 0), parsed.get("center", {}).get("y", 0)
        r = parsed.get("radius", 0)
        pts = [{"x": cx - r, "y": cy - r}, {"x": cx + r, "y": cy + r}]
    elif etype == "ARC":
        cx, cy = parsed.get("center", {}).get("x", 0), parsed.get("center", {}).get("y", 0)
        r = parsed.get("radius", 0)
        pts = [{"x": cx - r, "y": cy - r}, {"x": cx + r, "y": cy + r}]
    elif etype in ("LWPOLYLINE", "POLYLINE"):
        pts = parsed.get("points", [])
    elif etype == "TEXT" or etype == "MTEXT":
        pts = [parsed.get("position", {})]
    elif etype == "INSERT":
        pts = [parsed.get("position", {})]
    elif etype == "ELLIPSE":
        cx, cy = parsed.get("center", {}).get("x", 0), parsed.get("center", {}).get("y", 0)
        pts = [{"x": cx, "y": cy}]
    elif etype == "SPLINE":
        pts = parsed.get("control_points", [])
    elif etype == "POINT":
        pts = [parsed.get("position", {})]
    elif etype == "SOLID" or etype == "3DFACE":
        pts = parsed.get("points", [])

    for pt in pts:
        x = pt.get("x", 0)
        y = pt.get("y", 0)
        if x < scope.get("min_x", float('inf')):
            scope["min_x"] = x
        if y < scope.get("min_y", float('inf')):
            scope["min_y"] = y
        if x > scope.get("max_x", float('-inf')):
            scope["max_x"] = x
        if y > scope.get("max_y", float('-inf')):
            scope["max_y"] = y


def _parse_entity(entity) -> Optional[dict]:
    """Convert an ezdxf entity to a simplified dict for frontend."""
    dxf = entity.dxf
    etype = entity.dxftype()
    base = {"type": etype, "layer": dxf.get("layer", "0")}

    try:
        color = dxf.get("color", 256)
        base["color"] = color
    except Exception:
        base["color"] = 256

    if etype == "LINE":
        return {**base,
                "start": {"x": dxf.start.x, "y": dxf.start.y},
                "end": {"x": dxf.end.x, "y": dxf.end.y}}

    elif etype == "CIRCLE":
        return {**base,
                "center": {"x": dxf.center.x, "y": dxf.center.y},
                "radius": dxf.radius}

    elif etype == "ARC":
        return {**base,
                "center": {"x": dxf.center.x, "y": dxf.center.y},
                "radius": dxf.radius,
                "start_angle": dxf.start_angle,
                "end_angle": dxf.end_angle}

    elif etype == "LWPOLYLINE":
        points = []
        for pt in entity.get_points(format="xyb"):
            points.append({"x": pt[0], "y": pt[1], "bulge": pt[2]})
        closed = entity.closed
        return {**base, "points": points, "closed": closed}

    elif etype == "POLYLINE":
        points = []
        for vertex in entity.vertices:
            loc = vertex.dxf.location
            points.append({"x": loc.x, "y": loc.y})
        closed = entity.is_closed
        return {**base, "points": points, "closed": closed}

    elif etype == "TEXT":
        insert = dxf.insert
        return {**base,
                "position": {"x": insert.x, "y": insert.y},
                "text": dxf.text,
                "height": dxf.get("height", 1.0),
                "rotation": dxf.get("rotation", 0.0)}

    elif etype == "MTEXT":
        insert = dxf.insert
        return {**base,
                "position": {"x": insert.x, "y": insert.y},
                "text": entity.plain_text(),
                "height": dxf.get("char_height", 1.0)}

    elif etype == "INSERT":
        insert = dxf.insert
        return {**base,
                "position": {"x": insert.x, "y": insert.y},
                "block_name": dxf.name,
                "x_scale": dxf.get("xscale", 1.0),
                "y_scale": dxf.get("yscale", 1.0),
                "rotation": dxf.get("rotation", 0.0)}

    elif etype == "ELLIPSE":
        center = dxf.center
        major_axis = dxf.major_axis
        return {**base,
                "center": {"x": center.x, "y": center.y},
                "major_axis": {"x": major_axis.x, "y": major_axis.y},
                "ratio": dxf.ratio,
                "start_param": dxf.start_param,
                "end_param": dxf.end_param}

    elif etype == "SPLINE":
        ctrl_pts = [{"x": p.x, "y": p.y} for p in entity.control_points]
        return {**base, "control_points": ctrl_pts, "degree": entity.dxf.get("degree", 3)}

    elif etype == "POINT":
        loc = dxf.location
        return {**base, "position": {"x": loc.x, "y": loc.y}}

    elif etype == "SOLID":
        points = []
        for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
            v = dxf.get(attr, None)
            if v:
                points.append({"x": v.x, "y": v.y})
        return {**base, "points": points}

    elif etype == "HATCH":
        # Skip complex hatches - too much data
        return None

    elif etype == "DIMENSION":
        return None

    return None


def get_dxf_bounds(file_path: str) -> dict:
    """Get the bounding box of a DXF file quickly."""
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')

    for entity in msp:
        etype = entity.dxftype()
        dxf = entity.dxf
        try:
            if etype == "LINE":
                for pt in (dxf.start, dxf.end):
                    min_x = min(min_x, pt.x)
                    min_y = min(min_y, pt.y)
                    max_x = max(max_x, pt.x)
                    max_y = max(max_y, pt.y)
            elif etype in ("CIRCLE", "ARC"):
                c = dxf.center
                r = dxf.radius
                min_x = min(min_x, c.x - r)
                min_y = min(min_y, c.y - r)
                max_x = max(max_x, c.x + r)
                max_y = max(max_y, c.y + r)
            elif etype == "LWPOLYLINE":
                for pt in entity.get_points(format="xy"):
                    min_x = min(min_x, pt[0])
                    min_y = min(min_y, pt[1])
                    max_x = max(max_x, pt[0])
                    max_y = max(max_y, pt[1])
            elif etype == "TEXT":
                ins = dxf.insert
                min_x = min(min_x, ins.x)
                min_y = min(min_y, ins.y)
                max_x = max(max_x, ins.x)
                max_y = max(max_y, ins.y)
        except Exception:
            continue

    if min_x == float('inf'):
        return {"min_x": 0, "min_y": 0, "max_x": 1000, "max_y": 1000}

    return {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}
