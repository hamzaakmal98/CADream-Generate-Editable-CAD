from __future__ import annotations

from dataclasses import replace

from cad_parser import dxf_to_render_json, load_dxf_from_bytes
from page_view_spec import LayerSpec, PageViewSpec
from planset_manifest import AUTO_GENERATED_PAGES
from planset_page_registry import get_page_registry_map
from planset_site_page_profiles import PAGE_TITLE_NAMING_SPECS
from planset_viewport_ml import predict_viewport_for_sheet
from view_spec_heuristics import HeuristicViewSpecConfig, make_view_specs_from_source


def predict_view_specs(normalized_dxf_bytes: bytes, _page_catalog: object = None) -> list[PageViewSpec]:
    doc = load_dxf_from_bytes(normalized_dxf_bytes)
    baseline_specs = make_view_specs_from_source(
        doc,
        config=HeuristicViewSpecConfig(
            include_overall_page=True,
            start_page_number=1,
            grid_rows=5,
            grid_cols=5,
            max_grid_pages=13,
            use_density_ranking=True,
        ),
    )
    if len(baseline_specs) < len(AUTO_GENERATED_PAGES):
        raise ValueError("ML predictor could not generate enough baseline specs")

    page_registry = get_page_registry_map()
    render_payload = dxf_to_render_json(doc, max_entities=50000)

    specs: list[PageViewSpec] = []
    for index, page_number in enumerate(AUTO_GENERATED_PAGES):
        base = baseline_specs[index]
        page_title = PAGE_TITLE_NAMING_SPECS.get(page_number, f"Auto Page {page_number}")
        spec = replace(base, page_number=page_number, page_name=page_title)

        entry = page_registry.get(page_number, {}) if isinstance(page_registry, dict) else {}
        sheet_code = entry.get("sheet_code") if isinstance(entry, dict) else None
        if isinstance(sheet_code, str) and sheet_code.strip():
            prediction = predict_viewport_for_sheet(render_payload, sheet_code)
            if prediction is not None:
                merged_layers = spec.layers
                if prediction.layer_include:
                    merged_layers = LayerSpec(
                        freeze=spec.layers.freeze,
                        include=tuple(sorted(set(spec.layers.include).union(prediction.layer_include))),
                    )
                spec = replace(spec, view_bounds=prediction.bounds, layers=merged_layers)

        specs.append(spec)

    return specs
