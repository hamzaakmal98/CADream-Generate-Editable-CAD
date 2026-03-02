from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

from planset_manifest import build_plan_set_manifest
from planset_auto_page_emitters import emit_auto_page_entities
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
