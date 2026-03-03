from __future__ import annotations

from pathlib import Path
from typing import Any

from planset_manifest import build_plan_set_manifest
from planset_template_sample import generate_common_template_sample_dxf


_STATIC_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "static_pages"


def _sheet_metadata_for_page(page: dict[str, Any], page_number: int) -> dict[str, Any]:
    sheet_code = page.get("sheet_code") if isinstance(page.get("sheet_code"), str) else ""
    page_title = f"Template Page {page_number}"
    if sheet_code:
        page_title = f"{sheet_code}"

    return {
        "sheet_number": str(page_number).zfill(2),
        "sheet_title": page_title,
        "scale": "As Noted",
        "revision": "A",
    }


def _build_fallback_template_payload(payload: dict[str, Any], page: dict[str, Any], page_number: int) -> dict[str, Any]:
    out = dict(payload)
    right_panel = out.get("right_panel_metadata") if isinstance(out.get("right_panel_metadata"), dict) else {}
    right_panel = dict(right_panel)
    right_panel["sheet_metadata"] = _sheet_metadata_for_page(page, page_number)
    out["right_panel_metadata"] = right_panel
    return out


def generate_static_template_page_dxf_files(payload: dict[str, Any]) -> dict[str, bytes]:
    manifest = build_plan_set_manifest(payload)
    pages = manifest.get("pages") if isinstance(manifest.get("pages"), list) else []

    output: dict[str, bytes] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        if page.get("sheet_mode") != "static_template":
            continue

        page_number = page.get("page_number")
        if not isinstance(page_number, int) or page_number <= 0:
            continue

        template_path = _STATIC_TEMPLATE_DIR / f"page-{str(page_number).zfill(2)}.dxf"
        filename = f"planset-page-{str(page_number).zfill(2)}.dxf"

        if template_path.exists():
            output[filename] = template_path.read_bytes()
            continue

        fallback_payload = _build_fallback_template_payload(payload, page, page_number)
        output[filename] = generate_common_template_sample_dxf(fallback_payload)

    return output
