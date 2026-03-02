from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanSetPdfRenderOptions:
    right_crop_gutter_mm: float
    left_panel_zoom: float
    top_title_strip_mm: float
    title_box_height_mm: float
    left_dest_expand_mm: float


def _resolve_float_option(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def resolve_pdf_render_options(payload: dict[str, Any]) -> PlanSetPdfRenderOptions:
    return PlanSetPdfRenderOptions(
        right_crop_gutter_mm=_resolve_float_option(payload, "fixed_left_crop_right_gutter_mm", 0.0),
        left_panel_zoom=_resolve_float_option(payload, "fixed_left_panel_zoom", 0.93),
        top_title_strip_mm=_resolve_float_option(payload, "fixed_left_crop_top_strip_mm", 30.0),
        title_box_height_mm=_resolve_float_option(payload, "generated_title_box_height_mm", 10.0),
        left_dest_expand_mm=_resolve_float_option(payload, "fixed_left_dest_expand_mm", 6.0),
    )
