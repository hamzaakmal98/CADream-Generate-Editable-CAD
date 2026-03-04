from __future__ import annotations

from io import BytesIO
import math
from typing import Any

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from cad_parser import dxf_to_render_json, extract_blocks, load_dxf_from_bytes, IGNORE_LAYERS

from planset_manifest import build_plan_set_manifest
from planset_auto_page_emitters import emit_auto_page_entities
from planset_sld_pages import (
    _normalize_sld_nodes,
    _normalize_sld_edges,
    _compute_transform_with_edges,
    _project_point,
    _anchor_point,
    _route_with_straight_preference,
    _orthogonalize_polyline,
    _perpendicular_offset_polyline,
    SYMBOL_CANVAS_WIDTH,
    CANVAS_NODE_HEIGHT,
    SYMBOL_DISPLAY_LABEL,
    PAGE_24,
    PAGE_25,
)
from planset_pdf_compositor import (
    compose_fixed_left_panels,
    fixed_page_numbers_from_manifest,
    mm_to_points,
    resolve_template_pdf_path,
)
from planset_pdf_options import resolve_pdf_render_options
from planset_pdf_titles import build_right_panel_metadata, resolve_generated_page_title


def _resolve_generated_page_title(payload: dict[str, Any], page_number: int) -> str:
    return resolve_generated_page_title(payload, page_number)


def _resolve_template_pdf_path(payload: dict[str, Any]):
    return resolve_template_pdf_path(payload)


def _draw_generated_title_box(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    title_text: str,
    right_crop_gutter_mm: float,
    title_box_height_mm: float,
) -> None:
    margin = 5 * mm
    panel_w = 82 * mm
    gutter = mm_to_points(max(0.0, right_crop_gutter_mm))

    left_x = margin
    right_x = page_w - margin - panel_w - gutter
    if right_x <= left_x + 20:
        return

    box_h = mm_to_points(max(6.0, title_box_height_mm))
    top_y = page_h - margin
    bottom_y = top_y - box_h

    _draw_box(pdf, left_x, bottom_y, right_x - left_x, box_h)
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString((left_x + right_x) / 2, bottom_y + box_h * 0.34, title_text[:110])


def _build_right_panel_metadata(payload: dict[str, Any], page_number: int) -> tuple[dict[str, str], bytes | None]:
    return build_right_panel_metadata(payload, page_number)


def _draw_box(pdf: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    pdf.rect(x, y, w, h)


def _draw_signature_box(
    pdf: canvas.Canvas,
    *,
    x: float,
    y_bottom: float,
    width: float,
    height: float,
    signature_image_bytes: bytes | None,
) -> None:
    inset = 2 * mm
    box_x = x + inset
    box_y = y_bottom + inset
    box_w = width - 2 * inset
    box_h = height - 2 * inset
    _draw_box(pdf, box_x, box_y, box_w, box_h)

    if not signature_image_bytes:
        pdf.setFont("Helvetica", 6.5)
        pdf.drawCentredString(x + width / 2, y_bottom + height / 2, "[Engineer Signature Image Placeholder]")
        return

    try:
        image = ImageReader(BytesIO(signature_image_bytes))
        img_w, img_h = image.getSize()
        if img_w <= 0 or img_h <= 0:
            raise ValueError("Invalid signature image dimensions")

        scale = min(box_w / img_w, box_h / img_h)
        draw_w = img_w * scale
        draw_h = img_h * scale
        draw_x = box_x + (box_w - draw_w) / 2
        draw_y = box_y + (box_h - draw_h) / 2
        pdf.drawImage(image, draw_x, draw_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
    except Exception:
        pdf.setFont("Helvetica", 6.2)
        pdf.drawCentredString(x + width / 2, y_bottom + height / 2, "[Invalid Engineer Signature Image]")



def _compute_content_bounds(
    entities: list[dict[str, Any]],
) -> tuple[float, float, float, float] | None:
    """Compute viewport bounds from content entities using Tukey-fence outlier removal.

    Uses IQR-based fencing (Q1 - 1.5*IQR, Q3 + 1.5*IQR) to robustly exclude
    title blocks or annotation entities that sit far outside the main site area,
    even when they represent 10–20 % of all entities.
    """
    xs: list[float] = []
    ys: list[float] = []

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("type") or "").upper()
        if entity_type == "LINE":
            p1 = entity.get("p1")
            p2 = entity.get("p2")
            if isinstance(p1, list) and len(p1) >= 2:
                xs.append(float(p1[0]))
                ys.append(float(p1[1]))
            if isinstance(p2, list) and len(p2) >= 2:
                xs.append(float(p2[0]))
                ys.append(float(p2[1]))
        elif entity_type == "LWPOLYLINE":
            for p in (entity.get("points") or []):
                if isinstance(p, list) and len(p) >= 2:
                    xs.append(float(p[0]))
                    ys.append(float(p[1]))
        elif entity_type in ("CIRCLE", "ARC"):
            c = entity.get("center")
            r = entity.get("r")
            if isinstance(c, list) and len(c) >= 2 and isinstance(r, (int, float)):
                cx, cy, rv = float(c[0]), float(c[1]), float(r)
                xs += [cx - rv, cx + rv]
                ys += [cy - rv, cy + rv]
        elif entity_type in ("TEXT", "MTEXT", "INSERT"):
            p = entity.get("pos")
            if isinstance(p, list) and len(p) >= 2:
                xs.append(float(p[0]))
                ys.append(float(p[1]))

    if len(xs) < 2 or len(ys) < 2:
        return None

    def _pct(arr: list[float], q: float) -> float:
        arr_s = sorted(arr)
        idx = q * (len(arr_s) - 1)
        lo = int(math.floor(idx))
        hi = min(lo + 1, len(arr_s) - 1)
        return arr_s[lo] + (idx - lo) * (arr_s[hi] - arr_s[lo])

    def _tukey_fence(vals: list[float]) -> tuple[float, float]:
        q1 = _pct(vals, 0.25)
        q3 = _pct(vals, 0.75)
        iqr = max(q3 - q1, 1e-9)
        return q1 - 1.5 * iqr, q3 + 1.5 * iqr

    # Apply Tukey fences to remove outlier clusters (e.g. far-away title blocks)
    x_lo, x_hi = _tukey_fence(xs)
    y_lo, y_hi = _tukey_fence(ys)
    xs_filt = [v for v in xs if x_lo <= v <= x_hi]
    ys_filt = [v for v in ys if y_lo <= v <= y_hi]

    # If fencing removed everything, fall back to raw min/max
    if not xs_filt or not ys_filt:
        xs_filt, ys_filt = xs, ys

    bx0, bx1 = min(xs_filt), max(xs_filt)
    by0, by1 = min(ys_filt), max(ys_filt)

    if bx1 <= bx0 or by1 <= by0:
        return None

    return bx0, by0, bx1, by1


def _transform_xy(x: float, y: float, *, tx: float, ty: float, rotation_deg: float, sx: float, sy: float) -> tuple[float, float]:
    px = float(x) * float(sx)
    py = float(y) * float(sy)
    angle = math.radians(float(rotation_deg))
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rx = px * cos_a - py * sin_a
    ry = px * sin_a + py * cos_a
    return (rx + float(tx), ry + float(ty))


def _transform_render_entity(
    entity: dict[str, Any],
    *,
    tx: float,
    ty: float,
    rotation_deg: float,
    sx: float,
    sy: float,
) -> dict[str, Any] | None:
    entity_type = str(entity.get("type") or "").upper()

    if entity_type == "LINE":
        p1 = entity.get("p1")
        p2 = entity.get("p2")
        if not (isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2):
            return None
        x1, y1 = _transform_xy(float(p1[0]), float(p1[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
        x2, y2 = _transform_xy(float(p2[0]), float(p2[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
        return {
            **entity,
            "p1": [x1, y1],
            "p2": [x2, y2],
        }

    if entity_type == "LWPOLYLINE":
        points = entity.get("points") if isinstance(entity.get("points"), list) else []
        out_points: list[list[float]] = []
        for point in points:
            if not isinstance(point, list) or len(point) < 2:
                continue
            x, y = _transform_xy(float(point[0]), float(point[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
            out_points.append([x, y])
        if len(out_points) < 2:
            return None
        return {
            **entity,
            "points": out_points,
        }

    if entity_type == "CIRCLE":
        center = entity.get("center")
        radius = entity.get("r")
        if not (isinstance(center, list) and len(center) >= 2 and isinstance(radius, (int, float))):
            return None
        cx, cy = _transform_xy(float(center[0]), float(center[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
        scale = max(0.0001, (abs(float(sx)) + abs(float(sy))) * 0.5)
        return {
            **entity,
            "center": [cx, cy],
            "r": abs(float(radius)) * scale,
        }

    if entity_type == "ARC":
        center = entity.get("center")
        radius = entity.get("r")
        start_angle = entity.get("start_angle")
        end_angle = entity.get("end_angle")
        if not (
            isinstance(center, list)
            and len(center) >= 2
            and isinstance(radius, (int, float))
            and isinstance(start_angle, (int, float))
            and isinstance(end_angle, (int, float))
        ):
            return None
        cx, cy = _transform_xy(float(center[0]), float(center[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
        scale = max(0.0001, (abs(float(sx)) + abs(float(sy))) * 0.5)
        return {
            **entity,
            "center": [cx, cy],
            "r": abs(float(radius)) * scale,
            "start_angle": float(start_angle) + float(rotation_deg),
            "end_angle": float(end_angle) + float(rotation_deg),
        }

    if entity_type in ("TEXT", "MTEXT"):
        pos = entity.get("pos")
        if not (isinstance(pos, list) and len(pos) >= 2):
            return None
        px, py = _transform_xy(float(pos[0]), float(pos[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
        return {
            **entity,
            "pos": [px, py],
        }

    if entity_type == "INSERT":
        pos = entity.get("pos")
        if not (isinstance(pos, list) and len(pos) >= 2):
            return None
        px, py = _transform_xy(float(pos[0]), float(pos[1]), tx=tx, ty=ty, rotation_deg=rotation_deg, sx=sx, sy=sy)
        return {
            **entity,
            "pos": [px, py],
            "rotation": float(entity.get("rotation", 0.0) or 0.0) + float(rotation_deg),
            "xscale": float(entity.get("xscale", 1.0) or 1.0) * float(sx),
            "yscale": float(entity.get("yscale", 1.0) or 1.0) * float(sy),
        }

    return entity


def _expand_insert_entities(
    entities: list[dict[str, Any]],
    block_entities: dict[str, Any],
    *,
    depth: int = 0,
    max_depth: int = 2,
    max_output: int = 120000,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    for entity in entities:
        if len(output) >= max_output:
            break
        if not isinstance(entity, dict):
            continue

        entity_type = str(entity.get("type") or "").upper()
        if entity_type != "INSERT":
            output.append(entity)
            continue

        if depth >= max_depth:
            output.append(entity)
            continue

        block_name = entity.get("name")
        block_items = block_entities.get(block_name) if isinstance(block_name, str) else None
        if not isinstance(block_items, list) or not block_items:
            output.append(entity)
            continue

        pos = entity.get("pos") if isinstance(entity.get("pos"), list) else [0.0, 0.0]
        tx = float(pos[0]) if len(pos) >= 1 and isinstance(pos[0], (int, float)) else 0.0
        ty = float(pos[1]) if len(pos) >= 2 and isinstance(pos[1], (int, float)) else 0.0
        rotation = float(entity.get("rotation", 0.0) or 0.0)
        sx = float(entity.get("xscale", 1.0) or 1.0)
        sy = float(entity.get("yscale", 1.0) or 1.0)

        transformed_children: list[dict[str, Any]] = []
        for child in block_items:
            if not isinstance(child, dict):
                continue
            transformed = _transform_render_entity(child, tx=tx, ty=ty, rotation_deg=rotation, sx=sx, sy=sy)
            if transformed is not None:
                transformed_children.append(transformed)

        if transformed_children:
            expanded_children = _expand_insert_entities(
                transformed_children,
                block_entities,
                depth=depth + 1,
                max_depth=max_depth,
                max_output=max_output - len(output),
            )
            output.extend(expanded_children)
        else:
            output.append(entity)

    return output


def _fixed_page_numbers_from_manifest(pages: list[dict[str, Any]]) -> list[int]:
    return fixed_page_numbers_from_manifest(pages)


def _compose_fixed_left_panels(
    *,
    base_pdf_bytes: bytes,
    template_path,
    fixed_page_numbers: list[int],
    right_crop_gutter_mm: float,
    left_panel_zoom: float,
    top_title_strip_mm: float,
    left_dest_expand_mm: float,
) -> bytes:
    return compose_fixed_left_panels(
        base_pdf_bytes=base_pdf_bytes,
        template_path=template_path,
        fixed_page_numbers=fixed_page_numbers,
        right_crop_gutter_mm=right_crop_gutter_mm,
        left_panel_zoom=left_panel_zoom,
        top_title_strip_mm=top_title_strip_mm,
        left_dest_expand_mm=left_dest_expand_mm,
    )


def _draw_right_template_panel(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    metadata: dict[str, str],
    signature_image_bytes: bytes | None,
) -> None:
    margin = 5 * mm
    panel_w = 82 * mm
    x = page_w - margin - panel_w
    y_bottom = margin
    y_top = page_h - margin

    _draw_box(pdf, margin, margin, page_w - 2 * margin, page_h - 2 * margin)
    pdf.line(x, y_bottom, x, y_top)

    y = y_top

    def heading_box(title: str, total_h_mm: float, heading_h_mm: float = 6.2) -> tuple[float, float]:
        nonlocal y
        total_h = total_h_mm * mm
        heading_h = heading_h_mm * mm
        section_bottom = y - total_h
        _draw_box(pdf, x, section_bottom, panel_w, total_h)
        pdf.line(x, y - heading_h, x + panel_w, y - heading_h)
        pdf.setFont("Helvetica-Bold", 7.1)
        pdf.drawString(x + 1.2 * mm, y - 4.6 * mm, title)
        return section_bottom, y - heading_h

    # 1) SYSTEM INFORMATION
    section_bottom, content_top = heading_box("SYSTEM INFORMATION", 38.0)
    pdf.setFont("Helvetica", 6.8)
    lines = [
        f"AC System Size: {metadata.get('AC System Size', '')}",
        f"Inverter Model: {metadata.get('Inverter Model', '')}",
        f"DC System Size: {metadata.get('DC System Size', '')}",
        f"BESS: {metadata.get('BESS', '')}",
    ]
    ty = content_top - 3.8 * mm
    for line in lines:
        pdf.drawString(x + 1.2 * mm, ty, line[:70])
        ty -= 3.45 * mm
    y = section_bottom

    # 2) CUSTOMER INFORMATION
    section_bottom, content_top = heading_box("CUSTOMER INFORMATION", 40.0)
    customer_lines = [
        f"Name: {metadata.get('Customer Name', '')}",
        f"Address: {metadata.get('Customer Address', '')}",
        f"Website: {metadata.get('Customer Website', '')}",
        f"Phone: {metadata.get('Customer Phone', '')}",
        f"Contact: {metadata.get('Customer Contact', '')}",
    ]
    ty = content_top - 3.8 * mm
    for line in customer_lines:
        pdf.drawString(x + 1.2 * mm, ty, line[:70])
        ty -= 3.25 * mm
    y = section_bottom

    # 3) ENGINEER OF RECORD (signature image)
    section_bottom, content_top = heading_box("ENGINEER OF RECORD", 40.0)
    _draw_signature_box(
        pdf,
        x=x,
        y_bottom=section_bottom,
        width=panel_w,
        height=(content_top - section_bottom),
        signature_image_bytes=signature_image_bytes,
    )
    y = section_bottom

    # 4) PREV/DATE/DESCRIPTION table with 8 rows
    table_h = 42 * mm
    table_bottom = y - table_h
    _draw_box(pdf, x, table_bottom, panel_w, table_h)
    header_h = 6 * mm
    pdf.line(x, y - header_h, x + panel_w, y - header_h)
    col_prev = x + 10 * mm
    col_date = x + 26 * mm
    pdf.line(col_prev, table_bottom, col_prev, y)
    pdf.line(col_date, table_bottom, col_date, y)
    pdf.setFont("Helvetica-Bold", 6.8)
    pdf.drawString(x + 1.0 * mm, y - 4.2 * mm, "PREV")
    pdf.drawString(col_prev + 1.0 * mm, y - 4.2 * mm, "DATE")
    pdf.drawString(col_date + 1.0 * mm, y - 4.2 * mm, "DESCRIPTION")
    row_h = (table_h - header_h) / 8
    for row in range(1, 8):
        y_row = y - header_h - row * row_h
        pdf.line(x, y_row, x + panel_w, y_row)
    y = table_bottom

    # 5) AHJ
    section_bottom, content_top = heading_box("AHJ", 18.0)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(x + 1.2 * mm, content_top - 3.8 * mm, metadata.get("AHJ", "")[:70])
    y = section_bottom

    # 6) EQORE PROJECT
    section_bottom, content_top = heading_box("EQORE PROJECT", 18.0)
    pdf.setFont("Helvetica", 6.8)
    pdf.drawString(x + 1.2 * mm, content_top - 3.8 * mm, metadata.get("EQORE Project", "")[:70])
    y = section_bottom

    # 7) DESIGNER
    section_bottom, content_top = heading_box("DESIGNER", 32.0)
    designer_lines = [
        f"Company: {metadata.get('Designer Company', '')}",
        f"Address: {metadata.get('Designer Address', '')}",
        f"Website: {metadata.get('Designer Website', '')}",
        f"Phone: {metadata.get('Designer Phone', '')}",
        f"Contact: {metadata.get('Designer Contact', '')}",
    ]
    pdf.setFont("Helvetica", 6.5)
    ty = content_top - 3.5 * mm
    for line in designer_lines:
        pdf.drawString(x + 1.2 * mm, ty, line[:70])
        ty -= 3.1 * mm
    y = section_bottom

    # 8) PAGE NOTES
    section_bottom, content_top = heading_box("PAGE NOTES", 22.0)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(x + 1.2 * mm, content_top - 3.8 * mm, metadata.get("Page Notes", "")[:70])
    y = section_bottom

    # 9) bottom small metadata grid
    meta_h = max(y - y_bottom, 16 * mm)
    meta_bottom = y - meta_h
    _draw_box(pdf, x, meta_bottom, panel_w, meta_h)
    labels = ["Scale", "Sheet", "Drawn By", "Checked By", "Approved By", "Date", "Sheet No", "Revision"]
    label_col = x + 20 * mm
    pdf.line(label_col, meta_bottom, label_col, y)
    row_h = meta_h / len(labels)
    for row in range(1, len(labels)):
        y_row = y - row * row_h
        pdf.line(x, y_row, x + panel_w, y_row)

    meta_values = {
        "Scale": metadata.get("Scale", "As Noted"),
        "Sheet": metadata.get("Sheet", ""),
        "Drawn By": metadata.get("Drawn By", ""),
        "Checked By": metadata.get("Checked By", ""),
        "Approved By": metadata.get("Approved By", ""),
        "Date": metadata.get("Date", ""),
        "Sheet No": metadata.get("Sheet No", ""),
        "Revision": metadata.get("Revision", ""),
    }
    pdf.setFont("Helvetica", 5.9)
    for idx, label in enumerate(labels):
        yt = y - idx * row_h - 4.2
        pdf.drawString(x + 0.8 * mm, yt, label)
        pdf.drawString(label_col + 0.8 * mm, yt, str(meta_values[label])[:40])


def _draw_content_preview(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    page_info: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    generation_mode = page_info.get("generation_mode")
    if generation_mode != "auto":
        return

    page_number = int(page_info.get("page_number", 0) or 0)
    if page_number <= 0:
        return

    # Prefer the original source DXF bytes for direct, reliable rendering.
    # Fall back to auto-page DXF if source bytes are not in this payload.
    _raw_source = payload.get("__source_dxf_bytes")
    if isinstance(_raw_source, (bytes, bytearray)):
        dxf_bytes_to_render: bytes | None = bytes(_raw_source)
    else:
        page_dxf_files = payload.get("__auto_page_dxf_files") if isinstance(payload.get("__auto_page_dxf_files"), dict) else {}
        dxf_key = f"planset-page-{str(page_number).zfill(2)}.dxf"
        _page_bytes = page_dxf_files.get(dxf_key)
        dxf_bytes_to_render = bytes(_page_bytes) if isinstance(_page_bytes, (bytes, bytearray)) else None

    if dxf_bytes_to_render is not None:
        try:
            source_doc = load_dxf_from_bytes(dxf_bytes_to_render)
            render_doc = dxf_to_render_json(source_doc, max_entities=60000)
            entities = render_doc.get("entities") if isinstance(render_doc, dict) else None
            if not isinstance(entities, list) or not entities:
                raise ValueError("DXF has no renderable entities")

            blocks = extract_blocks(source_doc, max_entities_per_block=12000)
            expanded_entities = _expand_insert_entities(entities, blocks)

            # Compute viewport from source DXF content, excluding CADREAM
            # overlay layers (which may be in screen/canvas coordinates).
            content_entities = [
                e for e in expanded_entities
                if isinstance(e, dict)
                and not str(e.get("layer") or "").upper().startswith("CADREAM")
                and str(e.get("layer") or "") not in IGNORE_LAYERS
            ]
            view_bounds = _compute_content_bounds(content_entities or expanded_entities)
            if view_bounds is None:
                raise ValueError("DXF bounds are degenerate")

            min_x, min_y, max_x, max_y = view_bounds
            if max_x <= min_x or max_y <= min_y:
                raise ValueError("DXF bounds are degenerate")

            clip_x1, clip_y1, clip_x2, clip_y2 = 24.0, 86.0, 312.0, 266.0
            clip_w = clip_x2 - clip_x1
            clip_h = clip_y2 - clip_y1

            src_w = max_x - min_x
            src_h = max_y - min_y
            fit = min(clip_w / src_w, clip_h / src_h)
            draw_w = src_w * fit
            draw_h = src_h * fit
            off_x = clip_x1 + (clip_w - draw_w) * 0.5
            off_y = clip_y1 + (clip_h - draw_h) * 0.5

            def map_xy(x_raw: float, y_raw: float) -> tuple[float, float]:
                x_mm = off_x + (x_raw - min_x) * fit
                y_mm = off_y + (y_raw - min_y) * fit
                return mm_to_points(x_mm), mm_to_points(y_mm)

            pdf.saveState()
            path = pdf.beginPath()
            path.rect(mm_to_points(clip_x1), mm_to_points(clip_y1), mm_to_points(clip_x2 - clip_x1), mm_to_points(clip_y2 - clip_y1))
            pdf.clipPath(path, stroke=0, fill=0)
            pdf.setLineWidth(0.7)

            for entity in expanded_entities:
                if not isinstance(entity, dict):
                    continue
                layer_name = str(entity.get("layer") or "").upper()
                if layer_name.startswith("CADREAM") or layer_name in IGNORE_LAYERS:
                    continue
                entity_type = str(entity.get("type") or "").upper()

                if entity_type == "LINE":
                    p1 = entity.get("p1")
                    p2 = entity.get("p2")
                    if isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2:
                        x1, y1 = map_xy(float(p1[0]), float(p1[1]))
                        x2, y2 = map_xy(float(p2[0]), float(p2[1]))
                        pdf.line(x1, y1, x2, y2)
                    continue

                if entity_type == "LWPOLYLINE":
                    points = entity.get("points") if isinstance(entity.get("points"), list) else []
                    path2 = pdf.beginPath()
                    started = False
                    first_x = first_y = 0.0
                    last_x = last_y = 0.0
                    for point in points:
                        if not isinstance(point, list) or len(point) < 2:
                            continue
                        x, y = map_xy(float(point[0]), float(point[1]))
                        if not started:
                            path2.moveTo(x, y)
                            first_x, first_y = x, y
                            started = True
                        else:
                            path2.lineTo(x, y)
                        last_x, last_y = x, y
                    if started:
                        if bool(entity.get("closed")) and (abs(last_x - first_x) > 1e-6 or abs(last_y - first_y) > 1e-6):
                            path2.lineTo(first_x, first_y)
                        pdf.drawPath(path2, stroke=1, fill=0)
                    continue

                if entity_type == "CIRCLE":
                    center = entity.get("center")
                    radius = entity.get("r")
                    if isinstance(center, list) and len(center) >= 2 and isinstance(radius, (int, float)):
                        cx, cy = map_xy(float(center[0]), float(center[1]))
                        radius_pt = mm_to_points(abs(float(radius)) * fit)
                        pdf.circle(cx, cy, radius_pt, stroke=1, fill=0)
                    continue

                if entity_type == "ARC":
                    center = entity.get("center")
                    radius = entity.get("r")
                    start_angle = entity.get("start_angle")
                    end_angle = entity.get("end_angle")
                    if (
                        isinstance(center, list)
                        and len(center) >= 2
                        and isinstance(radius, (int, float))
                        and isinstance(start_angle, (int, float))
                        and isinstance(end_angle, (int, float))
                    ):
                        cx, cy = map_xy(float(center[0]), float(center[1]))
                        radius_pt = mm_to_points(abs(float(radius)) * fit)
                        pdf.arc(
                            cx - radius_pt,
                            cy - radius_pt,
                            cx + radius_pt,
                            cy + radius_pt,
                            float(start_angle),
                            float(end_angle),
                        )
                    continue

                if entity_type == "INSERT":
                    pos = entity.get("pos")
                    if isinstance(pos, list) and len(pos) >= 2:
                        px, py = map_xy(float(pos[0]), float(pos[1]))
                        half = mm_to_points(1.8)
                        pdf.rect(px - half, py - half, 2 * half, 2 * half, stroke=1, fill=0)
                    continue

                if entity_type in ("TEXT", "MTEXT"):
                    text = entity.get("text")
                    pos = entity.get("pos")
                    if isinstance(text, str) and isinstance(pos, list) and len(pos) >= 2:
                        pdf.setFont("Helvetica", 6)
                        tx, ty = map_xy(float(pos[0]), float(pos[1]))
                        pdf.drawString(tx, ty, text[:72])

            pdf.restoreState()
            return
        except Exception:
            pass

    entities = emit_auto_page_entities(payload, page_number)
    if not entities:
        return

    pdf.saveState()
    pdf.setLineWidth(0.8)

    def _mm_to_x(mm_x: float) -> float:
        return mm_to_points(mm_x)

    def _mm_to_y(mm_y: float) -> float:
        return mm_to_points(mm_y)

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        kind = entity.get("kind")
        data = entity.get("data") if isinstance(entity.get("data"), dict) else {}

        if kind == "polyline":
            raw_points = data.get("points") if isinstance(data.get("points"), list) else []
            points: list[tuple[float, float]] = []
            for point in raw_points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                x_raw, y_raw = point[0], point[1]
                if isinstance(x_raw, (int, float)) and isinstance(y_raw, (int, float)):
                    points.append((_mm_to_x(float(x_raw)), _mm_to_y(float(y_raw))))

            if len(points) >= 2:
                path = pdf.beginPath()
                path.moveTo(points[0][0], points[0][1])
                for x, y in points[1:]:
                    path.lineTo(x, y)
                pdf.drawPath(path, stroke=1, fill=0)
            continue

        if kind == "circle":
            center = data.get("center") if isinstance(data.get("center"), (list, tuple)) else None
            radius = data.get("r")
            if (
                isinstance(center, (list, tuple))
                and len(center) >= 2
                and isinstance(center[0], (int, float))
                and isinstance(center[1], (int, float))
                and isinstance(radius, (int, float))
            ):
                pdf.circle(_mm_to_x(float(center[0])), _mm_to_y(float(center[1])), mm_to_points(float(radius)), stroke=1, fill=0)
            continue

        if kind == "text":
            text_value = data.get("text")
            x_value = data.get("x")
            y_value = data.get("y")
            text_h_mm = data.get("height")
            if isinstance(text_value, str) and isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
                font_size = mm_to_points(float(text_h_mm)) if isinstance(text_h_mm, (int, float)) else 6.5
                pdf.setFont("Helvetica", max(5.5, min(12.0, font_size)))
                pdf.drawString(_mm_to_x(float(x_value)), _mm_to_y(float(y_value)), text_value[:72])
            continue

        if kind == "block_insert":
            x_value = data.get("x")
            y_value = data.get("y")
            block_name = data.get("block_name") if isinstance(data.get("block_name"), str) else "BLOCK"
            if isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
                px = _mm_to_x(float(x_value))
                py = _mm_to_y(float(y_value))
                marker = mm_to_points(1.6)
                pdf.rect(px - marker, py - marker, marker * 2.0, marker * 2.0, stroke=1, fill=0)
                pdf.setFont("Helvetica", 5.6)
                pdf.drawString(px + mm_to_points(1.8), py + mm_to_points(1.2), block_name[:30])

    pdf.restoreState()


def _draw_sld_page_content(
    pdf: canvas.Canvas,
    *,
    page_w: float,
    page_h: float,
    page_number: int,
    payload: dict[str, Any],
) -> None:
    sld_session = payload.get("sld_session")
    if not isinstance(sld_session, dict):
        return

    nodes = _normalize_sld_nodes(sld_session)
    edges = _normalize_sld_edges(sld_session)
    if not nodes:
        return

    transform = _compute_transform_with_edges(nodes, edges)

    node_points: dict[str, tuple[float, float]] = {}
    node_symbol_types: dict[str, str] = {}
    for node in nodes:
        symbol_type = node["symbol_type"]
        source_width = SYMBOL_CANVAS_WIDTH.get(symbol_type, 120.0)
        center_x = node["x"] + source_width / 2
        center_y = node["y"] + CANVAS_NODE_HEIGHT / 2
        node_points[node["id"]] = _project_point(center_x, center_y, transform)
        node_symbol_types[node["id"]] = symbol_type

    projected_edges: list[dict[str, Any]] = []
    for edge in edges:
        projected_points = [_project_point(x, y, transform) for x, y in edge["points"]] if edge["points"] else []
        projected_edges.append({**edge, "points": projected_points})

    three_line = page_number == PAGE_25

    pdf.saveState()
    pdf.setLineWidth(0.7)
    for node in nodes:
        symbol_type = node["symbol_type"]
        display_label = SYMBOL_DISPLAY_LABEL.get(symbol_type, node["label"])
        x_mm, y_mm = node_points[node["id"]]
        px = x_mm * mm
        py = y_mm * mm

        if symbol_type in {"utility-grid", "load"}:
            pdf.circle(px, py, 8.5 * mm, stroke=1, fill=0)
        else:
            pdf.rect(px - 15.0 * mm, py - 9.0 * mm, 30.0 * mm, 18.0 * mm, stroke=1, fill=0)

        pdf.setFont("Helvetica", 5.5)
        pdf.drawCentredString(px, py - 1.5 * mm, display_label[:22])

    pdf.setLineWidth(0.5)
    for edge in projected_edges:
        from_center = node_points.get(edge["from_node_id"])
        to_center = node_points.get(edge["to_node_id"])
        if not from_center or not to_center:
            continue

        points = edge["points"]
        start_toward_x = to_center[0]
        end_toward_x = from_center[0]
        if isinstance(points, list) and len(points) >= 2:
            start_toward_x = points[1][0]
            end_toward_x = points[-2][0]

        from_anchor = _anchor_point(from_center, node_symbol_types.get(edge["from_node_id"], ""), start_toward_x)
        to_anchor = _anchor_point(to_center, node_symbol_types.get(edge["to_node_id"], ""), end_toward_x)
        polyline_pts = _route_with_straight_preference(from_anchor, to_anchor, points)
        polyline_pts = _orthogonalize_polyline(polyline_pts)

        if len(polyline_pts) < 2:
            continue

        offsets = [-1.5, 0.0, 1.5] if three_line else [0.0]
        for offset in offsets:
            offset_pts = _perpendicular_offset_polyline(polyline_pts, offset)
            path = pdf.beginPath()
            path.moveTo(offset_pts[0][0] * mm, offset_pts[0][1] * mm)
            for xp, yp in offset_pts[1:]:
                path.lineTo(xp * mm, yp * mm)
            pdf.drawPath(path, stroke=1, fill=0)

    pdf.restoreState()


def generate_planset_fixed_pages_pdf(payload: dict[str, Any]) -> bytes:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []
    fixed_page_numbers = _fixed_page_numbers_from_manifest(pages)

    full_pdf = generate_planset_pages_pdf(payload)
    full_reader = PdfReader(BytesIO(full_pdf))
    writer = PdfWriter()
    fixed_set = set(fixed_page_numbers)
    for idx, page in enumerate(full_reader.pages):
        if (idx + 1) in fixed_set:
            writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def generate_planset_pages_pdf(payload: dict[str, Any]) -> bytes:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []
    fixed_page_numbers = _fixed_page_numbers_from_manifest(pages)
    options = resolve_pdf_render_options(payload)

    page_size = landscape(A3)
    page_w, page_h = page_size

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=page_size)

    for page in pages:
        if not isinstance(page, dict):
            continue

        page_number = int(page.get("page_number", 0))
        metadata, signature_image_bytes = _build_right_panel_metadata(payload, page_number)
        metadata["Sheet No"] = str(page_number).zfill(2)
        if not metadata.get("Sheet"):
            metadata["Sheet"] = f"Page {page_number}"

        generated_title_text = _resolve_generated_page_title(payload, page_number)

        _draw_generated_title_box(
            pdf,
            page_w=page_w,
            page_h=page_h,
            title_text=generated_title_text,
            right_crop_gutter_mm=options.right_crop_gutter_mm,
            title_box_height_mm=options.title_box_height_mm,
        )

        _draw_right_template_panel(
            pdf,
            page_w=page_w,
            page_h=page_h,
            metadata=metadata,
            signature_image_bytes=signature_image_bytes,
        )
        if page_number in (PAGE_24, PAGE_25):
            _draw_sld_page_content(pdf, page_w=page_w, page_h=page_h, page_number=page_number, payload=payload)
        else:
            _draw_content_preview(pdf, page_w=page_w, page_h=page_h, page_info=page, payload=payload)
        pdf.showPage()

    pdf.save()
    base_pdf_bytes = stream.getvalue()

    template_path = _resolve_template_pdf_path(payload)
    if not template_path.exists():
        raise FileNotFoundError(f"Template PDF not found: {template_path}")

    return _compose_fixed_left_panels(
        base_pdf_bytes=base_pdf_bytes,
        template_path=template_path,
        fixed_page_numbers=fixed_page_numbers,
        right_crop_gutter_mm=options.right_crop_gutter_mm,
        left_panel_zoom=options.left_panel_zoom,
        top_title_strip_mm=options.top_title_strip_mm,
        left_dest_expand_mm=options.left_dest_expand_mm,
    )
