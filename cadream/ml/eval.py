"""Evaluate the trained model against the teacher heuristic on one or more DXF files.

Usage (from repo root):
    cd cadream/ml
    python eval.py ../../sample-files/Input_Sample_0.dxf

Or evaluate all samples:
    python eval.py ../../sample-files/Input_Sample_*.dxf

Output per file
---------------
  - Console: bounding-box coordinates, which source was selected (model vs teacher),
    quality scores, and whether inference fell back.
  - PNG images (saved next to the DXF):
      <name>_eval_site.png      -- site-plan channel with teacher/model boxes
      <name>_eval_equip.png     -- equipment channel with teacher/model boxes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure the backend ml package is importable when running from cadream/ml/
_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import numpy as np

from cad_parser import dxf_to_render_json, load_dxf_from_bytes
from ml import EQUIPMENT_LAYOUT, SITE_PLAN
from ml.convert import img_norm_to_model_bbox
from ml.gates import box_metrics, choose_box
from ml.infer import DEFAULT_MODEL_PATH, _load_project_model_predictor
from ml.layer_stats import compute_layer_stats
from ml.normalize import normalize_dxf_bytes
from ml.rasterize import rasterize_render_doc_4ch
from ml.teacher import DEFAULT_VIEWPORT_ASPECT, generate_teacher_payload


def _draw_box_on_img(img_rgb: np.ndarray, box_xyxy: list[float], color: tuple[int, int, int], thickness: int = 2) -> None:
    """Draw a normalized xyxy box on an [H,W,3] uint8 image in-place."""
    h, w = img_rgb.shape[:2]
    x1 = max(0, int(round(box_xyxy[0] * w)))
    y1 = max(0, int(round(box_xyxy[1] * h)))
    x2 = min(w - 1, int(round(box_xyxy[2] * w)))
    y2 = min(h - 1, int(round(box_xyxy[3] * h)))
    for t in range(thickness):
        y1t, y2t = max(0, y1 - t), min(h - 1, y2 + t)
        x1t, x2t = max(0, x1 - t), min(w - 1, x2 + t)
        img_rgb[y1t, x1t:x2t] = color
        img_rgb[y2t, x1t:x2t] = color
        img_rgb[y1t:y2t, x1t] = color
        img_rgb[y1t:y2t, x2t] = color


def _save_eval_image(
    channel_img: np.ndarray,
    teacher_box: list[float],
    model_box: list[float] | None,
    chosen_source: str,
    out_path: Path,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print(f"  [skip PNG] Pillow not installed — run: pip install Pillow")
        return

    rgb = np.stack([channel_img, channel_img, channel_img], axis=-1).copy()

    # Teacher box: blue
    _draw_box_on_img(rgb, teacher_box, color=(64, 64, 255), thickness=2)
    # Model box: red (if available)
    if model_box is not None:
        _draw_box_on_img(rgb, model_box, color=(255, 64, 64), thickness=2)

    img = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(img)
    legend = f"BLUE=teacher  RED=model  SELECTED={chosen_source.upper()}"
    draw.text((4, 4), legend, fill=(255, 255, 0))
    img.save(out_path)
    print(f"  Saved: {out_path}")


def eval_dxf(dxf_path: Path, model_path: Path, viewport_aspect: float = DEFAULT_VIEWPORT_ASPECT) -> dict:
    print(f"\n{'='*60}")
    print(f"  {dxf_path.name}")
    print(f"{'='*60}")

    dxf_bytes = dxf_path.read_bytes()
    normalized = normalize_dxf_bytes(dxf_bytes)
    doc = load_dxf_from_bytes(normalized)
    render_doc = dxf_to_render_json(doc, max_entities=50000)

    layer_stats, global_bbox = compute_layer_stats(render_doc)
    input_4ch = rasterize_render_doc_4ch(render_doc, out_size=512)
    all_img = input_4ch[0]
    equip_img = input_4ch[1] if input_4ch.shape[0] > 1 else input_4ch[0]
    site_context_img = input_4ch[2] if input_4ch.shape[0] > 2 else all_img
    boundary_img = input_4ch[4] if input_4ch.shape[0] > 4 else np.zeros_like(all_img)
    site_gate_img = np.maximum(site_context_img, boundary_img)

    teacher_model, teacher_img, teacher_conf, teacher_debug = generate_teacher_payload(
        render_doc, viewport_aspect=viewport_aspect
    )

    print(f"\n  Teacher (heuristic) predictions:")
    for page_type in [SITE_PLAN, EQUIPMENT_LAYOUT]:
        bb = teacher_img[page_type]["bbox"]
        conf = float(teacher_conf[page_type])
        strategy = teacher_debug.get(page_type, {}).get("strategy", "?")
        print(f"    {page_type:20s}  box={[f'{v:.3f}' for v in bb]}  conf={conf:.2f}  strategy={strategy}")

    # Try model inference
    model_img: dict | None = None
    fallback_reason: str | None = None
    try:
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        predict_boxes = _load_project_model_predictor()
        image_tensor = (input_4ch.astype(np.float32) / 255.0)[None, :, :, :]
        model_pred = predict_boxes(str(model_path), image_tensor)
        model_pred = np.asarray(model_pred, dtype=np.float32).reshape(-1, 2, 4)
        model_img = {
            SITE_PLAN: [float(v) for v in model_pred[0, 0, :]],
            EQUIPMENT_LAYOUT: [float(v) for v in model_pred[0, 1, :]],
        }
        print(f"\n  Model predictions:")
        for page_type in [SITE_PLAN, EQUIPMENT_LAYOUT]:
            bb = model_img[page_type]
            print(f"    {page_type:20s}  box={[f'{v:.3f}' for v in bb]}")
    except Exception as exc:
        fallback_reason = str(exc)
        print(f"\n  Model inference FAILED (will use teacher): {exc}")

    # Box selection
    print(f"\n  Box selection (quality gates):")
    selected: dict[str, dict] = {}
    for page_type in [SITE_PLAN, EQUIPMENT_LAYOUT]:
        teacher_bb = teacher_img[page_type]["bbox"]
        teacher_c = float(teacher_conf[page_type])
        gate_img = site_gate_img if page_type == SITE_PLAN else equip_img
        metrics_t = box_metrics(gate_img, teacher_bb)

        if model_img is not None:
            model_bb = model_img[page_type]
            model_bbox_obj = img_norm_to_model_bbox(model_bb, global_bbox)
            metrics_m = box_metrics(gate_img, model_bb)
            chosen_bb, chosen_source, info = choose_box(
                page_type, teacher_bb, teacher_c, model_bb, teacher_c,
                metrics_t, metrics_m, model_bbox_obj, layer_stats,
            )
        else:
            chosen_bb = teacher_bb
            chosen_source = "teacher"
            metrics_m = {}
            info = {"fallback": fallback_reason}

        selected[page_type] = {"box": chosen_bb, "source": chosen_source, "info": info}
        print(f"    {page_type:20s}  selected={chosen_source.upper():8s}  box={[f'{v:.3f}' for v in chosen_bb]}")
        if model_img:
            t_density = metrics_t.get("density_rel", 0.0)
            m_density = metrics_m.get("density_rel", 0.0)
            print(f"      teacher density={t_density:.3f}  model density={m_density:.3f}")

    # Save visualizations
    stem = dxf_path.stem
    site_box_teacher = teacher_img[SITE_PLAN]["bbox"]
    site_box_model = model_img[SITE_PLAN] if model_img else None
    equip_box_teacher = teacher_img[EQUIPMENT_LAYOUT]["bbox"]
    equip_box_model = model_img[EQUIPMENT_LAYOUT] if model_img else None

    site_channel = np.clip(all_img, 0, 255).astype(np.uint8)
    equip_channel = np.clip(equip_img * 255, 0, 255).astype(np.uint8) if equip_img.max() <= 1.0 else np.clip(equip_img, 0, 255).astype(np.uint8)

    _save_eval_image(site_channel, site_box_teacher, site_box_model,
                     selected[SITE_PLAN]["source"],
                     dxf_path.parent / f"{stem}_eval_site.png")
    _save_eval_image(equip_channel, equip_box_teacher, equip_box_model,
                     selected[EQUIPMENT_LAYOUT]["source"],
                     dxf_path.parent / f"{stem}_eval_equip.png")

    return {"path": str(dxf_path), "selected": selected, "fallback_reason": fallback_reason}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate ML model against teacher heuristic on DXF files.")
    parser.add_argument("dxf_files", nargs="+", type=Path, help="One or more .dxf files to evaluate")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Path to model.pt")
    parser.add_argument("--viewport_aspect", type=float, default=DEFAULT_VIEWPORT_ASPECT)
    args = parser.parse_args()

    print(f"Model: {args.model}  (exists={args.model.exists()})")

    results = []
    for dxf_path in args.dxf_files:
        if not dxf_path.exists():
            print(f"WARNING: file not found: {dxf_path}")
            continue
        result = eval_dxf(dxf_path, model_path=args.model, viewport_aspect=args.viewport_aspect)
        results.append(result)

    # Summary
    if results:
        print(f"\n{'='*60}")
        print(f"  SUMMARY ({len(results)} files)")
        print(f"{'='*60}")
        for r in results:
            name = Path(r["path"]).name
            site_src = r["selected"][SITE_PLAN]["source"].upper()
            equip_src = r["selected"][EQUIPMENT_LAYOUT]["source"].upper()
            fb = " [FALLBACK]" if r["fallback_reason"] else ""
            print(f"  {name:30s}  site={site_src:8s}  equip={equip_src}{fb}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
