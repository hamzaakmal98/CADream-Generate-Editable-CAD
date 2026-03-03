from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cad_parser import dxf_to_render_json, load_dxf_from_bytes
from ml import EQUIPMENT_LAYOUT, SITE_PLAN
from ml.layer_stats import BBox
from ml.normalize import normalize_dxf_bytes
from ml.rasterize import rasterize_render_doc, rasterize_render_doc_4ch
from ml.streaming_stats import compute_uncapped_dxf_stats
from ml.teacher import DEFAULT_VIEWPORT_ASPECT, generate_teacher_payload


def _norm_name(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())


def _find_boundary_bbox_model(layer_stats: dict[str, dict[str, Any]]) -> list[float] | None:
    exact_key = "unit area boundary"
    fallback_keys = ["property", "boundary", "parcel", "lot", "easement", "setback"]

    for layer_name, payload in layer_stats.items():
        if _norm_name(layer_name) != exact_key:
            continue
        bbox = payload.get("bbox") if isinstance(payload, dict) else None
        if isinstance(bbox, BBox) and bbox.is_valid():
            return [float(bbox.minx), float(bbox.miny), float(bbox.maxx), float(bbox.maxy)]

    selected: list[BBox] = []
    for layer_name, payload in layer_stats.items():
        normalized = _norm_name(layer_name)
        if not any(key in normalized for key in fallback_keys):
            continue
        bbox = payload.get("bbox") if isinstance(payload, dict) else None
        if isinstance(bbox, BBox) and bbox.is_valid():
            selected.append(bbox)

    if not selected:
        return None
    union = selected[0]
    for bbox in selected[1:]:
        union = union.union(bbox)
    return [float(union.minx), float(union.miny), float(union.maxx), float(union.maxy)]


def _save_gray_png(image_array: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_array.astype(np.uint8), mode="L").save(output_path)


def _stable_seed(value: str) -> int:
    seed = 0
    for idx, ch in enumerate(value):
        seed = (seed + (idx + 1) * ord(ch)) % (2**31 - 1)
    return int(seed)


def _crop_dims(global_bbox: BBox, scale: float, aspect: float) -> tuple[float, float]:
    full_w = max(1e-6, global_bbox.maxx - global_bbox.minx)
    full_h = max(1e-6, global_bbox.maxy - global_bbox.miny)
    crop_w = full_w * max(0.05, float(scale))
    crop_h = full_h * max(0.05, float(scale))

    target_aspect = max(1e-6, float(aspect))
    current_aspect = crop_w / max(1e-6, crop_h)
    if current_aspect < target_aspect:
        crop_w = crop_h * target_aspect
    else:
        crop_h = crop_w / target_aspect
    return float(crop_w), float(crop_h)


def _clamp_center(value: float, min_value: float, max_value: float) -> float:
    if min_value > max_value:
        return 0.5 * (min_value + max_value)
    return float(max(min_value, min(max_value, value)))


def _make_crop(global_bbox: BBox, center_x: float, center_y: float, scale: float, aspect: float) -> BBox:
    crop_w, crop_h = _crop_dims(global_bbox, scale=scale, aspect=aspect)
    half_w = 0.5 * crop_w
    half_h = 0.5 * crop_h
    cx = _clamp_center(center_x, global_bbox.minx + half_w, global_bbox.maxx - half_w)
    cy = _clamp_center(center_y, global_bbox.miny + half_h, global_bbox.maxy - half_h)
    return BBox(float(cx - half_w), float(cy - half_h), float(cx + half_w), float(cy + half_h))


def _sample_mixed_crops(
    *,
    global_bbox: BBox,
    crop_count: int,
    aspect: float,
    equip_bbox: BBox | None,
    site_bbox: BBox | None,
    boundary_bbox: BBox | None,
    seed: int,
) -> list[tuple[BBox, str, float]]:
    count = max(1, int(crop_count))
    equip_n = int(round(count * 0.60))
    # If boundary_bbox exists, ensure at least 50% of SITE_PLAN crops are boundary-centered
    if boundary_bbox is not None:
        site_n = int(round(count * 0.30))  # 30% for site crops
        boundary_n = int(round(count * 0.20))  # 20% for explicit boundary crops (added below)
    else:
        site_n = int(round(count * 0.20))
        boundary_n = 0
    rand_n = max(0, count - equip_n - site_n - boundary_n)

    default_scales = np.asarray([0.35, 0.50, 0.70, 1.00], dtype=np.float64)
    rng = np.random.default_rng(int(seed))
    width = max(1e-6, global_bbox.maxx - global_bbox.minx)
    height = max(1e-6, global_bbox.maxy - global_bbox.miny)

    def _anchor_center(anchor: BBox | None) -> tuple[float, float]:
        if anchor is None:
            return _bbox_center(global_bbox)
        return _bbox_center(anchor)

    def _make_from_anchor(anchor: BBox | None, count_local: int, source: str, scales_override: list[float] | None = None) -> list[tuple[BBox, str, float]]:
        out: list[tuple[BBox, str, float]] = []
        ax, ay = _anchor_center(anchor)
        local_scales = np.asarray(scales_override, dtype=np.float64) if scales_override else default_scales
        for _ in range(max(0, int(count_local))):
            scale = float(rng.choice(local_scales))
            jitter_x = float(rng.normal(0.0, 0.10 * width * scale))
            jitter_y = float(rng.normal(0.0, 0.10 * height * scale))
            crop = _make_crop(global_bbox, ax + jitter_x, ay + jitter_y, scale=scale, aspect=aspect)
            out.append((crop, source, scale))
        return out

    crops: list[tuple[BBox, str, float]] = []
    crops.extend(_make_from_anchor(equip_bbox, equip_n, "equip_anchor"))

    site_scales: list[float] = []
    if site_n > 0:
        n_10 = int(round(0.40 * site_n))
        n_07 = int(round(0.30 * site_n))
        n_05 = int(round(0.20 * site_n))
        n_rand = max(0, site_n - n_10 - n_07 - n_05)
        site_scales.extend([1.0] * n_10)
        site_scales.extend([0.7] * n_07)
        site_scales.extend([0.5] * n_05)
        for _ in range(n_rand):
            site_scales.append(float(rng.uniform(0.35, 1.0)))
        if len(site_scales) < site_n:
            site_scales.extend([1.0] * (site_n - len(site_scales)))
        site_scales = site_scales[:site_n]
        rng.shuffle(site_scales)

    # Add explicit boundary-centered crops (at least 50% of site+boundary crops)
    boundary_scales = []
    if boundary_n > 0:
        n_10 = int(round(0.40 * boundary_n))
        n_07 = int(round(0.30 * boundary_n))
        n_05 = int(round(0.20 * boundary_n))
        n_rand = max(0, boundary_n - n_10 - n_07 - n_05)
        boundary_scales.extend([1.0] * n_10)
        boundary_scales.extend([0.7] * n_07)
        boundary_scales.extend([0.5] * n_05)
        for _ in range(n_rand):
            boundary_scales.append(float(rng.uniform(0.35, 1.0)))
        if len(boundary_scales) < boundary_n:
            boundary_scales.extend([1.0] * (boundary_n - len(boundary_scales)))
        boundary_scales = boundary_scales[:boundary_n]
        rng.shuffle(boundary_scales)

    # Split site crops: half boundary-centered, half site-centered
    if boundary_bbox is not None:
        half = (site_n + boundary_n) // 2
        crops.extend(_make_from_anchor(boundary_bbox, half, "site_anchor_boundary", scales_override=site_scales[:half] + boundary_scales[:half]))
        crops.extend(_make_from_anchor(site_bbox, site_n + boundary_n - half, "site_anchor", scales_override=site_scales[half:] + boundary_scales[half:]))
    else:
        if site_n > 0:
            crops.extend(_make_from_anchor(site_bbox, site_n, "site_anchor", scales_override=site_scales))

    for _ in range(rand_n):
        scale = float(rng.choice(default_scales))
        cx = float(rng.uniform(global_bbox.minx, global_bbox.maxx))
        cy = float(rng.uniform(global_bbox.miny, global_bbox.maxy))
        crop = _make_crop(global_bbox, cx, cy, scale=scale, aspect=aspect)
        crops.append((crop, "random", scale))

    return crops[:count]


def _intersection(a: BBox, b: BBox) -> BBox | None:
    minx = max(a.minx, b.minx)
    miny = max(a.miny, b.miny)
    maxx = min(a.maxx, b.maxx)
    maxy = min(a.maxy, b.maxy)
    inter = BBox(minx, miny, maxx, maxy) if maxx > minx and maxy > miny else None
    return inter if inter and inter.is_valid() else None


def _to_crop_norm(box: BBox, crop: BBox) -> list[float]:
    crop_w = max(1e-9, crop.maxx - crop.minx)
    crop_h = max(1e-9, crop.maxy - crop.miny)
    x1 = (box.minx - crop.minx) / crop_w
    y1 = (box.miny - crop.miny) / crop_h
    x2 = (box.maxx - crop.minx) / crop_w
    y2 = (box.maxy - crop.miny) / crop_h
    return [
        float(max(0.0, min(1.0, x1))),
        float(max(0.0, min(1.0, y1))),
        float(max(0.0, min(1.0, x2))),
        float(max(0.0, min(1.0, y2))),
    ]


def _as_bbox(values: list[float]) -> BBox:
    x1, y1, x2, y2 = [float(v) for v in values]
    return BBox(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _bbox_center(box: BBox) -> tuple[float, float]:
    return (0.5 * (box.minx + box.maxx), 0.5 * (box.miny + box.maxy))


def _normalized_center_distance(a: BBox, b: BBox, reference: BBox) -> float:
    ax, ay = _bbox_center(a)
    bx, by = _bbox_center(b)
    dx = ax - bx
    dy = ay - by
    ref_w = max(1e-9, reference.maxx - reference.minx)
    ref_h = max(1e-9, reference.maxy - reference.miny)
    ref_diag = max(1e-9, math.hypot(ref_w, ref_h))
    return float(math.hypot(dx, dy) / ref_diag)


def _emit_crop_records(
    *,
    case_dir: Path,
    render_doc: dict[str, Any],
    teacher_boxes_model: dict[str, Any],
    teacher_conf: dict[str, float],
    boundary_bbox_model: list[float] | None,
    global_bbox: BBox,
    out_size: int,
    viewport_aspect: float,
    crop_count: int,
    min_label_intersection: float,
) -> dict[str, Any]:
    site_payload = teacher_boxes_model.get(SITE_PLAN) if isinstance(teacher_boxes_model, dict) else None
    site_values = site_payload.get("bbox") if isinstance(site_payload, dict) else None
    site_teacher_box = _as_bbox(site_values) if isinstance(site_values, list) and len(site_values) == 4 else None
    equip_payload = teacher_boxes_model.get(EQUIPMENT_LAYOUT) if isinstance(teacher_boxes_model, dict) else None
    equip_values = equip_payload.get("bbox") if isinstance(equip_payload, dict) else None
    equip_teacher_box = _as_bbox(equip_values) if isinstance(equip_values, list) and len(equip_values) == 4 else None

    boundary_bbox = _as_bbox(boundary_bbox_model) if isinstance(boundary_bbox_model, list) and len(boundary_bbox_model) == 4 else None

    # If boundary exists, set min_label_intersection higher for SITE_PLAN
    min_label_intersection_site = 0.35 if boundary_bbox is not None else min_label_intersection
    crops = _sample_mixed_crops(
        global_bbox=global_bbox,
        crop_count=int(crop_count),
        aspect=float(viewport_aspect),
        equip_bbox=equip_teacher_box,
        site_bbox=site_teacher_box,
        boundary_bbox=boundary_bbox,
        seed=_stable_seed(case_dir.name),
    )

    crop_summary: list[dict[str, Any]] = []

    for crop_index, (crop_bbox, crop_source, crop_scale) in enumerate(crops):
        crop_dir = case_dir / "crops" / str(crop_index)
        crop_dir.mkdir(parents=True, exist_ok=True)

        crop_tensor = rasterize_render_doc_4ch(render_doc, out_size=out_size, bounds_override=(crop_bbox.minx, crop_bbox.miny, crop_bbox.maxx, crop_bbox.maxy))
        np.save(crop_dir / "input.npy", crop_tensor.astype(np.uint8))

        labels: dict[str, list[float]] = {}
        weights: dict[str, float] = {}
        confidences: dict[str, float] = {}
        presence: dict[str, float] = {
            SITE_PLAN: 0.0,
            EQUIPMENT_LAYOUT: 0.0,
        }


        for page_key in (SITE_PLAN, EQUIPMENT_LAYOUT):
            payload = teacher_boxes_model.get(page_key) if isinstance(teacher_boxes_model, dict) else None
            bbox_values = payload.get("bbox") if isinstance(payload, dict) else None
            if not isinstance(bbox_values, list) or len(bbox_values) != 4:
                confidences[page_key] = 0.0
                weights[page_key] = 0.0
                continue

            teacher_box = _as_bbox(bbox_values)
            inter = _intersection(teacher_box, crop_bbox)
            if inter is None:
                weights[page_key] = 0.0
                confidences[page_key] = 0.0
                continue

            teacher_area = max(1e-9, teacher_box.area())
            inter_ratio = inter.area() / teacher_area
            # Use higher min_label_intersection for SITE_PLAN if boundary exists
            min_inter = min_label_intersection_site if page_key == SITE_PLAN else min_label_intersection
            if inter_ratio < float(min_inter):
                weights[page_key] = 0.0
                confidences[page_key] = 0.0
                presence[page_key] = 0.0
                continue

            labels[page_key] = _to_crop_norm(inter, crop_bbox)
            conf = float(teacher_conf.get(page_key, 0.0)) if isinstance(teacher_conf, dict) else 0.0
            conf_adj = float(max(0.0, min(1.0, conf * inter_ratio)))
            confidences[page_key] = conf_adj
            weights[page_key] = conf_adj
            presence[page_key] = 1.0

        confidences.setdefault(SITE_PLAN, 0.0)
        confidences.setdefault(EQUIPMENT_LAYOUT, 0.0)
        weights.setdefault(SITE_PLAN, 0.0)
        weights.setdefault(EQUIPMENT_LAYOUT, 0.0)

        labels_payload = {
            "schema_version": "ml-crop-labels-v1",
            "crop_index": crop_index,
            "labels": labels,
            "presence": {
                SITE_PLAN: float(presence.get(SITE_PLAN, 0.0)),
                EQUIPMENT_LAYOUT: float(presence.get(EQUIPMENT_LAYOUT, 0.0)),
            },
        }
        weights_payload = {
            "schema_version": "ml-crop-weights-v1",
            "crop_index": crop_index,
            "confidences": {
                SITE_PLAN: float(confidences.get(SITE_PLAN, 0.0)),
                EQUIPMENT_LAYOUT: float(confidences.get(EQUIPMENT_LAYOUT, 0.0)),
            },
            "weights": {
                SITE_PLAN: float(weights.get(SITE_PLAN, 0.0)),
                EQUIPMENT_LAYOUT: float(weights.get(EQUIPMENT_LAYOUT, 0.0)),
            },
        }

        (crop_dir / "labels.json").write_text(json.dumps(labels_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (crop_dir / "weights.json").write_text(json.dumps(weights_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        crop_summary.append(
            {
                "crop_index": crop_index,
                "path": str((crop_dir / "input.npy").relative_to(case_dir).as_posix()),
                "source": crop_source,
                "scale": float(crop_scale),
                "labels": sorted(labels.keys()),
                "presence": labels_payload["presence"],
                "confidences": weights_payload["confidences"],
                "weights": weights_payload["weights"],
            }
        )

    return {
        "count": len(crops),
        "items": crop_summary,
    }


def build_dataset(
    input_dir: Path,
    out_dir: Path,
    out_size: int = 512,
    viewport_aspect: float = DEFAULT_VIEWPORT_ASPECT,
    crop_count: int = 64,
    min_label_intersection: float = 0.20,
) -> dict[str, Any]:
    dxf_files = sorted(input_dir.glob("Input_Sample_*.dxf"))
    if not dxf_files:
        raise FileNotFoundError(f"No Input_Sample_*.dxf files found in: {input_dir}")

    summary: list[dict[str, Any]] = []
    index_records: list[dict[str, Any]] = []

    for dxf_file in dxf_files:
        case_id = dxf_file.stem
        case_dir = out_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        source_bytes = normalize_dxf_bytes(dxf_file.read_bytes())
        doc = load_dxf_from_bytes(source_bytes)
        uncapped_stats, uncapped_global_bbox, uncapped_entity_count = compute_uncapped_dxf_stats(doc)
        render_doc = dxf_to_render_json(doc, max_entities=50000)

        input_4ch = rasterize_render_doc_4ch(render_doc, out_size=out_size)
        input_img = input_4ch[0]
        density_img = rasterize_render_doc(render_doc, out_size=out_size, mode="density")
        np.save(case_dir / "input_4ch.npy", input_4ch.astype(np.uint8))
        _save_gray_png(input_img, case_dir / "input.png")
        _save_gray_png(density_img, case_dir / "density.png")

        teacher_boxes_model, teacher_boxes_img, teacher_conf, teacher_debug = generate_teacher_payload(
            render_doc,
            viewport_aspect=float(viewport_aspect),
            stats_override=uncapped_stats,
            global_bbox_override=uncapped_global_bbox,
        )

        bounds = {
            "min": [uncapped_global_bbox.minx, uncapped_global_bbox.miny],
            "max": [uncapped_global_bbox.maxx, uncapped_global_bbox.maxy],
        }
        layer_counts = teacher_debug.get("layer_counts") if isinstance(teacher_debug, dict) else {}
        top_layer_counts = dict(list(layer_counts.items())[:30]) if isinstance(layer_counts, dict) else {}

        boundary_bbox_model = _find_boundary_bbox_model(uncapped_stats)

        meta = {
            "file": dxf_file.name,
            "case_id": case_id,
            "global_bounds": bounds,
            "boundary_bbox_model": boundary_bbox_model,
            "viewport_aspect": float(viewport_aspect),
            "entity_count": int(uncapped_entity_count),
            "channels": [
                "all_non_noise",
                "equipment_layers_only",
                "site_context_layers_only",
                "noise_layers_only",
            ],
            "layer_counts_top": top_layer_counts,
        }

        (case_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "teacher_boxes_model.json").write_text(json.dumps(teacher_boxes_model, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "teacher_boxes_img.json").write_text(json.dumps(teacher_boxes_img, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "teacher_confidence.json").write_text(json.dumps(teacher_conf, indent=2, ensure_ascii=False), encoding="utf-8")
        (case_dir / "debug_teacher.json").write_text(json.dumps(teacher_debug, indent=2, ensure_ascii=False), encoding="utf-8")

        crop_manifest = _emit_crop_records(
            case_dir=case_dir,
            render_doc=render_doc,
            teacher_boxes_model=teacher_boxes_model,
            teacher_conf=teacher_conf,
            boundary_bbox_model=boundary_bbox_model,
            global_bbox=uncapped_global_bbox,
            out_size=out_size,
            viewport_aspect=float(viewport_aspect),
            crop_count=int(crop_count),
            min_label_intersection=float(min_label_intersection),
        )
        (case_dir / "crops_manifest.json").write_text(json.dumps(crop_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        summary.append(
            {
                "case_id": case_id,
                "file": dxf_file.name,
                "entity_count": meta["entity_count"],
                "teacher_confidence": teacher_conf,
                "crop_count": int(crop_manifest["count"]),
            }
        )

        index_records.append(
            {
                "record_type": "case",
                "case_id": case_id,
                "file": dxf_file.name,
                "confidence": teacher_conf,
                "paths": {
                    "meta": str((case_dir / "meta.json").relative_to(out_dir).as_posix()),
                    "teacher_confidence": str((case_dir / "teacher_confidence.json").relative_to(out_dir).as_posix()),
                    "teacher_boxes_img": str((case_dir / "teacher_boxes_img.json").relative_to(out_dir).as_posix()),
                    "input_4ch_npy": str((case_dir / "input_4ch.npy").relative_to(out_dir).as_posix()),
                    "input_png": str((case_dir / "input.png").relative_to(out_dir).as_posix()),
                },
            }
        )

        for crop_item in crop_manifest.get("items", []):
            crop_index = int(crop_item.get("crop_index", -1))
            input_rel = f"{case_id}/crops/{crop_index}/input.npy"
            labels_rel = f"{case_id}/crops/{crop_index}/labels.json"
            weights_rel = f"{case_id}/crops/{crop_index}/weights.json"
            index_records.append(
                {
                    "record_type": "crop",
                    "case_id": case_id,
                    "crop_id": crop_index,
                    "input_path": input_rel,
                    "labels_path": labels_rel,
                    "weights_path": weights_rel,
                    "source": crop_item.get("source"),
                    "scale": crop_item.get("scale"),
                }
            )

    payload = {
        "schema_version": "ml-dataset-v2",
        "input_dir": str(input_dir),
        "out_dir": str(out_dir),
        "cases": summary,
    }
    (out_dir / "dataset_summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    index_path = out_dir / "index.jsonl"
    with index_path.open("w", encoding="utf-8") as handle:
        for record in index_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ML teacher dataset from DXF files.")
    parser.add_argument("--input_dir", default="../../sample-files", help="Directory containing Input_Sample_*.dxf files")
    parser.add_argument("--out_dir", default="../../dataset", help="Output dataset directory")
    parser.add_argument("--size", type=int, default=512, help="Output raster size")
    parser.add_argument("--viewport_aspect", type=float, default=DEFAULT_VIEWPORT_ASPECT, help="Viewport aspect ratio")
    parser.add_argument("--crop_count", type=int, default=64, help="Number of fixed-aspect crops per case")
    parser.add_argument("--min_label_intersection", type=float, default=0.20, help="Minimum intersection ratio to keep crop label")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    result = build_dataset(
        input_dir=input_dir,
        out_dir=out_dir,
        out_size=max(128, int(args.size)),
        viewport_aspect=max(0.1, float(args.viewport_aspect)),
        crop_count=max(1, int(args.crop_count)),
        min_label_intersection=max(0.0, min(1.0, float(args.min_label_intersection))),
    )
    print(f"Built dataset at: {out_dir}")
    print(f"Cases: {len(result['cases'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
