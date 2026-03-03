from __future__ import annotations

from io import StringIO
from math import cos, radians, sin
from typing import Any

import ezdxf

from planset_manifest import build_plan_set_manifest


def _serialize_doc(doc: ezdxf.document.Drawing) -> bytes:
    stream = StringIO()
    doc.write(stream)
    encoding = getattr(doc, "output_encoding", None) or "cp1252"
    return stream.getvalue().encode(encoding, errors="replace")


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_param_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    entities = payload.get("site_placements", {}).get("entities", {}) if isinstance(payload.get("site_placements"), dict) else {}
    bess_list = entities.get("bess") if isinstance(entities.get("bess"), list) else []
    first = bess_list[0] if bess_list and isinstance(bess_list[0], dict) else {}

    cad_insert = first.get("cad_insert") if isinstance(first.get("cad_insert"), dict) else {}
    model_name = first.get("label") if isinstance(first.get("label"), str) and first.get("label") else "BESS Model"

    params = {
        "rotation": _safe_float(cad_insert.get("rotation"), 0.0),
        "pad_height": _safe_float(first.get("pad_height"), 0.4),
        "conduit_side": str(first.get("conduit_entry_side") or "east"),
        "model_name": model_name,
    }
    return params


def _ensure_layers(doc: ezdxf.document.Drawing) -> None:
    for name, color in (
        ("CADREAM-PARAM-BORDER", 8),
        ("CADREAM-PARAM-EQUIP", 7),
        ("CADREAM-PARAM-ANNO", 5),
        ("CADREAM-PARAM-TITLE", 6),
    ):
        if name not in doc.layers:
            doc.layers.add(name)
        doc.layers.get(name).dxf.color = color


def _add_border(layout: Any) -> None:
    points = [(0, 0), (420, 0), (420, 297), (0, 297)]
    poly = layout.add_lwpolyline(points, dxfattribs={"layer": "CADREAM-PARAM-BORDER"})
    poly.closed = True


def _rect_points(cx: float, cy: float, w: float, h: float, rotation_deg: float) -> list[tuple[float, float]]:
    hw = w * 0.5
    hh = h * 0.5
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

    theta = radians(rotation_deg)
    cos_t = cos(theta)
    sin_t = sin(theta)

    out: list[tuple[float, float]] = []
    for x, y in corners:
        rx = x * cos_t - y * sin_t
        ry = x * sin_t + y * cos_t
        out.append((cx + rx, cy + ry))
    return out


def _draw_top_view(layout: Any, params: dict[str, Any], sheet_code: str) -> None:
    cx, cy = 170.0, 170.0
    equip = _rect_points(cx, cy, 120.0, 55.0, params["rotation"])
    poly = layout.add_lwpolyline(equip, dxfattribs={"layer": "CADREAM-PARAM-EQUIP"})
    poly.closed = True

    layout.add_text(f"{sheet_code} Top View", dxfattribs={"layer": "CADREAM-PARAM-TITLE", "height": 3.5}).set_placement((20, 280))
    layout.add_text(f"Model: {params['model_name']}", dxfattribs={"layer": "CADREAM-PARAM-ANNO", "height": 2.5}).set_placement((20, 265))
    layout.add_text(f"Conduit Entry: {params['conduit_side']}", dxfattribs={"layer": "CADREAM-PARAM-ANNO", "height": 2.5}).set_placement((20, 257))


def _draw_elevation(layout: Any, params: dict[str, Any], sheet_code: str, direction: str) -> None:
    x0, y0 = 70.0, 90.0
    width = 200.0
    height = 90.0

    poly = layout.add_lwpolyline(
        [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height)],
        dxfattribs={"layer": "CADREAM-PARAM-EQUIP"},
    )
    poly.closed = True

    pad_h = max(0.1, min(3.0, float(params["pad_height"])))
    layout.add_line((x0 - 20, y0), (x0 + width + 20, y0), dxfattribs={"layer": "CADREAM-PARAM-EQUIP"})
    layout.add_text(f"{sheet_code} {direction} Elevation", dxfattribs={"layer": "CADREAM-PARAM-TITLE", "height": 3.5}).set_placement((20, 280))
    layout.add_text(f"Pad Height: {pad_h:.2f} m", dxfattribs={"layer": "CADREAM-PARAM-ANNO", "height": 2.5}).set_placement((20, 258))


def _draw_slab_detail(layout: Any, params: dict[str, Any], sheet_code: str) -> None:
    x0, y0 = 60.0, 95.0
    slab_w = 240.0
    slab_h = 45.0
    poly = layout.add_lwpolyline(
        [(x0, y0), (x0 + slab_w, y0), (x0 + slab_w, y0 + slab_h), (x0, y0 + slab_h)],
        dxfattribs={"layer": "CADREAM-PARAM-EQUIP"},
    )
    poly.closed = True

    conduit_side = str(params["conduit_side"]).lower()
    conduit_x = x0 + slab_w - 20 if conduit_side == "east" else x0 + 20
    layout.add_line((conduit_x, y0 - 10), (conduit_x, y0 + slab_h + 10), dxfattribs={"layer": "CADREAM-PARAM-ANNO"})
    layout.add_text(f"{sheet_code} Slab / Beam Detail", dxfattribs={"layer": "CADREAM-PARAM-TITLE", "height": 3.5}).set_placement((20, 280))
    layout.add_text(f"Conduit Side: {params['conduit_side']}", dxfattribs={"layer": "CADREAM-PARAM-ANNO", "height": 2.5}).set_placement((20, 258))


def _build_parametric_page(page: dict[str, Any], payload: dict[str, Any]) -> bytes:
    page_number = int(page["page_number"])
    sheet_code = str(page.get("sheet_code") or f"ESS-{page_number}")

    doc = ezdxf.new("R2013")
    _ensure_layers(doc)
    layout = doc.modelspace()
    _add_border(layout)

    params = _extract_param_inputs(payload)

    if "15.0" in sheet_code:
        _draw_slab_detail(layout, params, sheet_code)
    elif page_number % 2 == 0:
        _draw_top_view(layout, params, sheet_code)
    else:
        direction = "West" if page_number % 4 == 1 else "East"
        _draw_elevation(layout, params, sheet_code, direction)

    return _serialize_doc(doc)


def generate_parametric_page_dxf_files(payload: dict[str, Any]) -> dict[str, bytes]:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []

    output: dict[str, bytes] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("sheet_mode") != "parametric_equipment_detail":
            continue

        page_number = page.get("page_number")
        if not isinstance(page_number, int) or page_number <= 0:
            continue

        filename = f"planset-page-{str(page_number).zfill(2)}.dxf"
        output[filename] = _build_parametric_page(page, payload)

    return output
