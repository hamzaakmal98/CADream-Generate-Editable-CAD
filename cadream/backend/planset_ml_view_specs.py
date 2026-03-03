from __future__ import annotations

from dataclasses import replace

from cad_parser import load_dxf_from_bytes
from ml.infer import DEFAULT_MODEL_PATH, predict_view_boxes_from_dxf
from page_view_spec import PageViewSpec
from planset_manifest import AUTO_GENERATED_PAGES
from planset_site_page_profiles import PAGE_TITLE_NAMING_SPECS
from view_spec_heuristics import HeuristicViewSpecConfig, make_view_specs_from_source


def predict_view_specs(normalized_dxf_bytes: bytes, _page_catalog: object = None) -> list[PageViewSpec]:
    cfg = HeuristicViewSpecConfig(
        include_overall_page=True,
        start_page_number=1,
        grid_rows=5,
        grid_cols=5,
        max_grid_pages=13,
        use_density_ranking=True,
    )

    doc = load_dxf_from_bytes(normalized_dxf_bytes)
    baseline_specs = make_view_specs_from_source(
        doc,
        config=cfg,
    )
    if len(baseline_specs) < len(AUTO_GENERATED_PAGES):
        raise ValueError("ML predictor could not generate enough baseline specs")

    vx1, vy1, vx2, vy2 = cfg.viewport_rect
    viewport_aspect = max(0.1, float(vx2 - vx1) / max(1e-9, float(vy2 - vy1)))

    inferred_specs = predict_view_boxes_from_dxf(
        normalized_dxf_bytes,
        model_path=str(DEFAULT_MODEL_PATH),
        viewport_aspect=viewport_aspect,
    )
    inferred_by_page: dict[int, PageViewSpec] = {spec.page_number: spec for spec in inferred_specs}

    specs: list[PageViewSpec] = []
    for index, page_number in enumerate(AUTO_GENERATED_PAGES):
        base = baseline_specs[index]
        page_title = PAGE_TITLE_NAMING_SPECS.get(page_number, f"Auto Page {page_number}")
        spec = replace(base, page_number=page_number, page_name=page_title)

        inferred = inferred_by_page.get(page_number)
        if inferred is not None:
            spec = replace(spec, view_bounds=inferred.view_bounds, layers=inferred.layers)

        specs.append(spec)

    return specs
