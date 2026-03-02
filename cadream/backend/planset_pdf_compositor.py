from __future__ import annotations

from io import BytesIO
from pathlib import Path
import threading
from typing import Any

from pypdf import PdfReader, PdfWriter, Transformation


_DEFAULT_TEMPLATE_PDF_PATH = Path(__file__).resolve().parents[2] / "sample-files" / "Template_Project.pdf"

_TEMPLATE_PDF_CACHE_LOCK = threading.Lock()
_TEMPLATE_PDF_CACHE: dict[str, tuple[float, int, bytes]] = {}


def mm_to_points(mm_value: float) -> float:
    return mm_value * 72.0 / 25.4


def resolve_template_pdf_path(payload: dict[str, Any]) -> Path:
    custom_value = payload.get("fixed_template_pdf_path")
    if isinstance(custom_value, str) and custom_value.strip():
        candidate = Path(custom_value.strip())
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[2] / candidate
        return candidate
    return _DEFAULT_TEMPLATE_PDF_PATH


def _load_template_pdf_bytes(template_path: Path) -> bytes:
    if not template_path.exists():
        raise FileNotFoundError(f"Template PDF not found: {template_path}")

    stat = template_path.stat()
    key = str(template_path.resolve())
    mtime = float(stat.st_mtime)
    size = int(stat.st_size)

    with _TEMPLATE_PDF_CACHE_LOCK:
        cached = _TEMPLATE_PDF_CACHE.get(key)
        if cached and cached[0] == mtime and cached[1] == size:
            return cached[2]

        data = template_path.read_bytes()
        _TEMPLATE_PDF_CACHE[key] = (mtime, size, data)
        return data


def fixed_page_numbers_from_manifest(pages: list[dict[str, Any]]) -> list[int]:
    fixed_pages: list[int] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("generation_mode") != "fixed":
            continue
        page_number = page.get("page_number")
        if isinstance(page_number, int) and page_number > 0:
            fixed_pages.append(page_number)
    return fixed_pages


def compose_fixed_left_panels(
    *,
    base_pdf_bytes: bytes,
    template_path: Path,
    fixed_page_numbers: list[int],
    right_crop_gutter_mm: float,
    left_panel_zoom: float,
    top_title_strip_mm: float,
    left_dest_expand_mm: float,
) -> bytes:
    base_reader = PdfReader(BytesIO(base_pdf_bytes))
    template_reader = PdfReader(BytesIO(_load_template_pdf_bytes(template_path)))
    writer = PdfWriter()

    fixed_page_set = set(fixed_page_numbers)

    for page_index, base_page in enumerate(base_reader.pages):
        page_number = page_index + 1
        writer.add_page(base_page)
        out_page = writer.pages[-1]

        if page_number not in fixed_page_set:
            continue

        template_index = page_number - 1
        if template_index >= len(template_reader.pages):
            raise ValueError(
                f"Template PDF has only {len(template_reader.pages)} pages; cannot map fixed page {page_number}"
            )

        page_w = float(out_page.mediabox.width)
        page_h = float(out_page.mediabox.height)
        margin = mm_to_points(5.0)
        panel_w = mm_to_points(82.0)
        split_x = page_w - margin - panel_w
        split_x_adjusted = split_x - mm_to_points(max(0.0, right_crop_gutter_mm))
        if split_x_adjusted <= margin:
            split_x_adjusted = split_x

        split_x_adjusted = split_x_adjusted + mm_to_points(max(0.0, left_dest_expand_mm))
        max_right = page_w - margin
        if split_x_adjusted > max_right:
            split_x_adjusted = max_right

        dest_x0 = margin
        dest_y0 = margin
        dest_x1 = split_x_adjusted
        dest_y1 = page_h - margin
        dest_w = dest_x1 - dest_x0
        dest_h = dest_y1 - dest_y0

        template_page_ref = template_reader.pages[template_index]
        template_w = float(template_page_ref.mediabox.width)
        template_h = float(template_page_ref.mediabox.height)

        src_x0 = template_w * (dest_x0 / page_w)
        src_x1 = template_w * (dest_x1 / page_w)
        src_y0 = template_h * (dest_y0 / page_h)
        src_y1 = template_h * (dest_y1 / page_h)
        src_y1 = src_y1 - mm_to_points(max(0.0, top_title_strip_mm))
        src_w = src_x1 - src_x0
        src_h = src_y1 - src_y0

        if src_w <= 0 or src_h <= 0 or dest_w <= 0 or dest_h <= 0:
            continue

        zoom = left_panel_zoom if 0 < left_panel_zoom <= 1.0 else 1.0
        fit = min(dest_w / src_w, dest_h / src_h) * zoom
        draw_w = src_w * fit
        draw_h = src_h * fit
        pad_x = (dest_w - draw_w) / 2
        pad_y = (dest_h - draw_h) / 2
        translate_x = dest_x0 + pad_x - src_x0 * fit
        translate_y = dest_y0 + pad_y - src_y0 * fit

        temp_writer = PdfWriter()
        temp_writer.add_page(template_page_ref)
        left_panel = temp_writer.pages[0]
        left_panel.cropbox.lower_left = (src_x0, src_y0)
        left_panel.cropbox.upper_right = (src_x1, src_y1)
        left_panel.trimbox.lower_left = (src_x0, src_y0)
        left_panel.trimbox.upper_right = (src_x1, src_y1)

        transform = Transformation().scale(fit, fit).translate(translate_x, translate_y)
        out_page.merge_transformed_page(left_panel, transform)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()
