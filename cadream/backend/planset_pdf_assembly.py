from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from cad_parser import dxf_to_render_json, load_dxf_from_bytes
from planset_page_registry import get_page_registry_entries


def _parse_page_number(file_name: str) -> int | None:
    token = file_name.replace("planset-page-", "").replace(".dxf", "")
    if token.isdigit():
        page_number = int(token)
        if page_number > 0:
            return page_number
    return None


def _fit_transform(bounds: dict[str, list[float]], frame: tuple[float, float, float, float]) -> tuple[float, float, float, float, float]:
    left, bottom, width, height = frame
    min_x, min_y = float(bounds["min"][0]), float(bounds["min"][1])
    max_x, max_y = float(bounds["max"][0]), float(bounds["max"][1])

    span_x = max(1e-6, max_x - min_x)
    span_y = max(1e-6, max_y - min_y)
    scale = min(width / span_x, height / span_y)

    draw_w = span_x * scale
    draw_h = span_y * scale
    ox = left + (width - draw_w) * 0.5
    oy = bottom + (height - draw_h) * 0.5
    return min_x, min_y, scale, ox, oy


def _tx(x: float, min_x: float, scale: float, ox: float) -> float:
    return ox + (x - min_x) * scale


def _ty(y: float, min_y: float, scale: float, oy: float) -> float:
    return oy + (y - min_y) * scale


def _draw_entity_preview(pdf: canvas.Canvas, entities: list[dict[str, Any]], transform: tuple[float, float, float, float, float]) -> None:
    min_x, min_y, scale, ox, oy = transform

    pdf.setStrokeColorRGB(0.12, 0.16, 0.22)
    pdf.setLineWidth(0.35)

    text_draw_limit = 120
    text_count = 0

    for entity in entities:
        entity_type = entity.get("type")

        if entity_type == "LINE":
            p1 = entity.get("p1")
            p2 = entity.get("p2")
            if isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2:
                pdf.line(
                    _tx(float(p1[0]), min_x, scale, ox),
                    _ty(float(p1[1]), min_y, scale, oy),
                    _tx(float(p2[0]), min_x, scale, ox),
                    _ty(float(p2[1]), min_y, scale, oy),
                )

        elif entity_type == "LWPOLYLINE":
            points = entity.get("points")
            if not isinstance(points, list) or len(points) < 2:
                continue
            prev = points[0]
            if not (isinstance(prev, list) and len(prev) >= 2):
                continue
            for point in points[1:]:
                if not (isinstance(point, list) and len(point) >= 2):
                    continue
                pdf.line(
                    _tx(float(prev[0]), min_x, scale, ox),
                    _ty(float(prev[1]), min_y, scale, oy),
                    _tx(float(point[0]), min_x, scale, ox),
                    _ty(float(point[1]), min_y, scale, oy),
                )
                prev = point

            if entity.get("closed") and isinstance(points[0], list) and len(points[0]) >= 2:
                first = points[0]
                pdf.line(
                    _tx(float(prev[0]), min_x, scale, ox),
                    _ty(float(prev[1]), min_y, scale, oy),
                    _tx(float(first[0]), min_x, scale, ox),
                    _ty(float(first[1]), min_y, scale, oy),
                )

        elif entity_type == "CIRCLE":
            center = entity.get("center")
            radius = entity.get("r")
            if isinstance(center, list) and len(center) >= 2 and isinstance(radius, (int, float)):
                pdf.circle(
                    _tx(float(center[0]), min_x, scale, ox),
                    _ty(float(center[1]), min_y, scale, oy),
                    abs(float(radius)) * scale,
                    stroke=1,
                    fill=0,
                )

        elif entity_type == "ARC":
            center = entity.get("center")
            radius = entity.get("r")
            a0 = entity.get("start_angle")
            a1 = entity.get("end_angle")
            if (
                isinstance(center, list)
                and len(center) >= 2
                and isinstance(radius, (int, float))
                and isinstance(a0, (int, float))
                and isinstance(a1, (int, float))
            ):
                steps = 18
                start = math.radians(float(a0))
                end = math.radians(float(a1))
                if end < start:
                    end += math.tau
                prev_x = float(center[0]) + float(radius) * math.cos(start)
                prev_y = float(center[1]) + float(radius) * math.sin(start)
                for idx in range(1, steps + 1):
                    t = start + (end - start) * idx / steps
                    x = float(center[0]) + float(radius) * math.cos(t)
                    y = float(center[1]) + float(radius) * math.sin(t)
                    pdf.line(
                        _tx(prev_x, min_x, scale, ox),
                        _ty(prev_y, min_y, scale, oy),
                        _tx(x, min_x, scale, ox),
                        _ty(y, min_y, scale, oy),
                    )
                    prev_x, prev_y = x, y

        elif entity_type in ("TEXT", "MTEXT") and text_count < text_draw_limit:
            pos = entity.get("pos")
            text = entity.get("text")
            if isinstance(pos, list) and len(pos) >= 2 and isinstance(text, str) and text.strip():
                text_count += 1
                pdf.setFont("Helvetica", 5)
                pdf.drawString(
                    _tx(float(pos[0]), min_x, scale, ox),
                    _ty(float(pos[1]), min_y, scale, oy),
                    text[:30],
                )


def build_ess_order_pdf_from_dxf_files(
    *,
    manifest: dict[str, Any],
    auto_files: dict[str, bytes],
    parametric_files: dict[str, bytes],
    static_files: dict[str, bytes],
) -> bytes:
    file_map: dict[int, bytes] = {}
    for collection in (auto_files, parametric_files, static_files):
        for file_name, content in collection.items():
            page_number = _parse_page_number(file_name)
            if page_number is None:
                continue
            file_map[page_number] = content

    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []
    sheet_by_page: dict[int, str] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_number = page.get("page_number")
        sheet_code = page.get("sheet_code")
        if isinstance(page_number, int) and isinstance(sheet_code, str):
            sheet_by_page[page_number] = sheet_code

    ordered_entries = get_page_registry_entries()
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=landscape(A3))
    page_w, page_h = landscape(A3)

    frame = (14 * mm, 14 * mm, page_w - 28 * mm, page_h - 36 * mm)

    for entry in ordered_entries:
        page_number = int(entry.get("page_number", 0) or 0)
        if page_number <= 0:
            continue

        sheet_code = sheet_by_page.get(page_number) or str(entry.get("sheet_code") or f"Page {page_number}")
        mode = str(entry.get("mode") or "")

        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(12 * mm, page_h - 10 * mm, f"{sheet_code}  |  Page {page_number}  |  Mode: {mode}")

        pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
        pdf.rect(frame[0], frame[1], frame[2], frame[3], stroke=1, fill=0)

        content = file_map.get(page_number)
        if content is None:
            pdf.setFont("Helvetica", 8)
            pdf.setFillColorRGB(0.45, 0.45, 0.45)
            pdf.drawString(20 * mm, page_h / 2, "No DXF artifact available for this page in current export mode.")
            pdf.showPage()
            continue

        try:
            doc = load_dxf_from_bytes(content)
            render_payload = dxf_to_render_json(doc, max_entities=25000)
            bounds = render_payload.get("bounds")
            entities = render_payload.get("entities")

            if not isinstance(bounds, dict) or not isinstance(entities, list):
                raise ValueError("DXF render payload missing bounds/entities")

            transform = _fit_transform(bounds, frame)
            _draw_entity_preview(pdf, entities, transform)
        except Exception as error:
            pdf.setFont("Helvetica", 8)
            pdf.setFillColorRGB(0.7, 0.2, 0.2)
            pdf.drawString(20 * mm, page_h / 2, f"Preview render error: {error}")

        pdf.showPage()

    pdf.save()
    return stream.getvalue()
