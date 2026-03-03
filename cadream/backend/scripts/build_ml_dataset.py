from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cad_parser import dxf_to_render_json, load_dxf_from_bytes
from ml.rasterize import rasterize_render_doc
from planset_manifest import AUTO_GENERATED_PAGES
from view_spec_heuristics import HeuristicViewSpecConfig, make_view_specs_from_source


LABEL_PAGE_TYPES = {
    "SITE_PLAN": 1,
    "PANEL_DETAIL": 4,
    "WORK_AREA": 6,
}


def _ensure_bounds(payload: dict[str, Any]) -> dict[str, Any]:
    bounds = payload.get("bounds") if isinstance(payload, dict) else None
    if not isinstance(bounds, dict):
        raise ValueError("render payload has no bounds")
    mn = bounds.get("min")
    mx = bounds.get("max")
    if not isinstance(mn, list) or not isinstance(mx, list) or len(mn) < 2 or len(mx) < 2:
        raise ValueError("render payload bounds invalid")
    return bounds


def _norm_box(view_bounds: dict[str, list[float]], render_bounds: dict[str, list[float]]) -> list[float]:
    min_x = float(render_bounds["min"][0])
    min_y = float(render_bounds["min"][1])
    max_x = float(render_bounds["max"][0])
    max_y = float(render_bounds["max"][1])

    span_x = max(1e-6, max_x - min_x)
    span_y = max(1e-6, max_y - min_y)

    bx0 = float(view_bounds["min"][0])
    by0 = float(view_bounds["min"][1])
    bx1 = float(view_bounds["max"][0])
    by1 = float(view_bounds["max"][1])

    nx0 = (bx0 - min_x) / span_x
    nx1 = (bx1 - min_x) / span_x
    ny0 = 1.0 - ((by0 - min_y) / span_y)
    ny1 = 1.0 - ((by1 - min_y) / span_y)

    x1 = max(0.0, min(1.0, min(nx0, nx1)))
    x2 = max(0.0, min(1.0, max(nx0, nx1)))
    y1 = max(0.0, min(1.0, min(ny0, ny1)))
    y2 = max(0.0, min(1.0, max(ny0, ny1)))
    return [round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6)]


def _bootstrap_labels(doc_bytes: bytes, render_bounds: dict[str, list[float]]) -> dict[str, list[float]]:
    doc = load_dxf_from_bytes(doc_bytes)
    specs = make_view_specs_from_source(
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

    by_page: dict[int, dict[str, Any]] = {}
    for index, page_number in enumerate(AUTO_GENERATED_PAGES):
        if index >= len(specs):
            break
        by_page[page_number] = specs[index].to_dict()["view_bounds"]

    labels: dict[str, list[float]] = {}
    for page_type, page_number in LABEL_PAGE_TYPES.items():
        if page_number in by_page:
            labels[page_type] = _norm_box(by_page[page_number], render_bounds)
    return labels


def _save_png(image_array: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_array, mode="RGBA").save(output_path)


def build_dataset(samples_dir: Path, dataset_dir: Path, out_size: int = 512, overwrite_labels: bool = False) -> dict[str, Any]:
    sample_files = sorted(samples_dir.glob("Input_Sample_*.dxf"))
    summary: list[dict[str, Any]] = []

    for sample_file in sample_files:
        case_id = sample_file.stem
        case_dir = dataset_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        source_bytes = sample_file.read_bytes()
        doc = load_dxf_from_bytes(source_bytes)
        render_payload = dxf_to_render_json(doc, max_entities=50000)
        render_bounds = _ensure_bounds(render_payload)

        image = rasterize_render_doc(render_payload, out_size=out_size)
        _save_png(image, case_dir / "input.png")

        layers = render_payload.get("layers") if isinstance(render_payload.get("layers"), list) else []
        meta = {
            "schema_version": "ml-dataset-input-meta-v1",
            "case_id": case_id,
            "source_file": sample_file.name,
            "image_size": out_size,
            "channels": ["all_geometry", "equipment", "cables", "boundary"],
            "bounds": render_bounds,
            "entity_count": len(render_payload.get("entities", [])),
            "layers": [layer.get("name") for layer in layers if isinstance(layer, dict) and isinstance(layer.get("name"), str)],
        }
        (case_dir / "input_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        labels_path = case_dir / "labels.json"
        if overwrite_labels or not labels_path.exists():
            labels = _bootstrap_labels(source_bytes, render_bounds)
            labels_payload = {
                "schema_version": "ml-dataset-labels-v1",
                "case_id": case_id,
                "labels": labels,
                "label_source": "heuristic-bootstrap",
            }
            labels_path.write_text(json.dumps(labels_payload, indent=2), encoding="utf-8")
        else:
            labels_payload = json.loads(labels_path.read_text(encoding="utf-8"))

        summary.append(
            {
                "case_id": case_id,
                "source": sample_file.name,
                "entity_count": meta["entity_count"],
                "labels": sorted(list((labels_payload.get("labels") or {}).keys())),
            }
        )

    result = {
        "schema_version": "ml-dataset-build-summary-v1",
        "samples_dir": str(samples_dir),
        "dataset_dir": str(dataset_dir),
        "cases": summary,
    }
    (dataset_dir / "dataset_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build viewport ML dataset from DXF samples.")
    parser.add_argument("--samples", default="../../sample-files", help="Directory containing Input_Sample_*.dxf files")
    parser.add_argument("--out", default="../../dataset", help="Output dataset directory")
    parser.add_argument("--size", type=int, default=512, help="Output raster size")
    parser.add_argument("--overwrite-labels", action="store_true", help="Overwrite existing labels.json")
    args = parser.parse_args()

    samples_dir = Path(args.samples).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    result = build_dataset(samples_dir, out_dir, out_size=max(128, args.size), overwrite_labels=args.overwrite_labels)
    print(f"Built dataset at: {out_dir}")
    print(f"Cases: {len(result['cases'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
