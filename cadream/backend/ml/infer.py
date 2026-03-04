from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

from cad_parser import dxf_to_render_json, load_dxf_from_bytes
from ml import EQUIPMENT_LAYOUT, SITE_PLAN
from ml.convert import img_norm_to_model_bbox, model_bbox_to_img_norm
from ml.gates import box_metrics, choose_box
from ml.layer_stats import BBox, compute_layer_stats
from ml.normalize import normalize_dxf_bytes
from ml.rasterize import rasterize_render_doc_4ch
from ml.teacher import DEFAULT_VIEWPORT_ASPECT, generate_teacher_payload
from page_view_spec import Bounds2D, LayerSpec, PageViewSpec, SheetSpec, TemplateSpec
from planset_site_page_profiles import PAGE_TITLE_NAMING_SPECS
from view_spec_heuristics import HeuristicViewSpecConfig


DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "ml" / "model.pt"
_RUN_REPORT_PATH = Path(__file__).resolve().parents[3] / "tmp" / "run_report.json"


def _load_project_model_predictor():
    project_ml_dir = Path(__file__).resolve().parents[2] / "ml"
    infer_py = project_ml_dir / "infer.py"
    if not infer_py.exists():
        raise FileNotFoundError(f"Model infer module not found: {infer_py}")

    spec = importlib.util.spec_from_file_location("cadream_project_ml_infer", infer_py)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load cadream/ml/infer.py")

    module = importlib.util.module_from_spec(spec)
    sys.modules["cadream_project_ml_infer"] = module
    spec.loader.exec_module(module)
    predict_fn = getattr(module, "predict_boxes", None)
    if predict_fn is None:
        raise RuntimeError("predict_boxes not found in cadream/ml/infer.py")
    return predict_fn


def _to_page_specs(site_bbox: BBox, equip_bbox: BBox) -> list[PageViewSpec]:
    cfg = HeuristicViewSpecConfig()

    site_bounds = Bounds2D(
        min_x=site_bbox.minx,
        min_y=site_bbox.miny,
        max_x=site_bbox.maxx,
        max_y=site_bbox.maxy,
    )
    equip_bounds = Bounds2D(
        min_x=equip_bbox.minx,
        min_y=equip_bbox.miny,
        max_x=equip_bbox.maxx,
        max_y=equip_bbox.maxy,
    )

    specs: list[PageViewSpec] = []
    specs.append(
        PageViewSpec(
            page_number=1,
            page_name=PAGE_TITLE_NAMING_SPECS.get(1, SITE_PLAN),
            view_bounds=site_bounds,
            sheet=SheetSpec(width=cfg.sheet_width, height=cfg.sheet_height, units=cfg.sheet_units),
            viewport_rect=cfg.viewport_rect,
            template=TemplateSpec(id=cfg.template_id, title_block_block_name=cfg.title_block_block_name),
            layers=LayerSpec(include=("Unit Area Boundary", "Base Map", "Road", "Obstruction", "Shading")),
            overlays=None,
        )
    )
    specs.append(
        PageViewSpec(
            page_number=2,
            page_name=PAGE_TITLE_NAMING_SPECS.get(2, EQUIPMENT_LAYOUT),
            view_bounds=equip_bounds,
            sheet=SheetSpec(width=cfg.sheet_width, height=cfg.sheet_height, units=cfg.sheet_units),
            viewport_rect=cfg.viewport_rect,
            template=TemplateSpec(id=cfg.template_id, title_block_block_name=cfg.title_block_block_name),
            layers=LayerSpec(include=("Inverter", "Module", "Transformer", "Combiner Box", "Service Panel", "Cable Path")),
            overlays=None,
        )
    )
    return specs


def infer_view_specs_from_dxf_bytes(dxf_bytes: bytes, model_path: str, viewport_aspect: float):
    """
    normalize -> parse -> compute stats/global bbox -> rasterize -> model predict
    convert model img boxes -> model bboxes -> run gates -> choose teacher/model
    return PageViewSpec objects for SITE_PLAN and EQUIPMENT_LAYOUT plus debug report
    """
    normalized = normalize_dxf_bytes(dxf_bytes)
    doc = load_dxf_from_bytes(normalized)
    render_doc = dxf_to_render_json(doc, max_entities=50000)

    layer_stats, global_bbox = compute_layer_stats(render_doc)
    input_4ch = rasterize_render_doc_4ch(render_doc, out_size=512)
    all_img = input_4ch[0]
    equip_gate_img = input_4ch[1] if input_4ch.shape[0] > 1 else all_img
    site_context_img = input_4ch[2] if input_4ch.shape[0] > 2 else all_img
    boundary_img = input_4ch[4] if input_4ch.shape[0] > 4 else np.zeros_like(all_img)
    site_gate_img = np.maximum(site_context_img, boundary_img)

    teacher_model, teacher_img, teacher_conf, teacher_debug = generate_teacher_payload(render_doc, viewport_aspect=viewport_aspect)

    selected_img = {
        SITE_PLAN: teacher_img[SITE_PLAN]["bbox"],
        EQUIPMENT_LAYOUT: teacher_img[EQUIPMENT_LAYOUT]["bbox"],
    }
    selection_debug: dict[str, Any] = {}

    try:
        predict_boxes = _load_project_model_predictor()
        image_tensor = (input_4ch.astype(np.float32) / 255.0)[None, :, :, :]
        model_pred = predict_boxes(str(model_path), image_tensor)
        model_pred = np.asarray(model_pred, dtype=np.float32).reshape(-1, 2, 4)
        model_img = {
            SITE_PLAN: [float(v) for v in model_pred[0, 0, :]],
            EQUIPMENT_LAYOUT: [float(v) for v in model_pred[0, 1, :]],
        }

        site_model_bbox = img_norm_to_model_bbox(model_img[SITE_PLAN], global_bbox)
        equip_model_bbox = img_norm_to_model_bbox(model_img[EQUIPMENT_LAYOUT], global_bbox)

        for page_type, model_bbox_obj in ((SITE_PLAN, site_model_bbox), (EQUIPMENT_LAYOUT, equip_model_bbox)):
            teacher_bb = teacher_img[page_type]["bbox"]
            teacher_c = float(teacher_conf[page_type])
            model_bb = model_img[page_type]
            model_c = teacher_c

            gate_img = site_gate_img if page_type == SITE_PLAN else equip_gate_img
            metrics_t = box_metrics(gate_img, teacher_bb)
            metrics_m = box_metrics(gate_img, model_bb)
            chosen_bb, chosen_source, info = choose_box(
                page_type,
                teacher_bb,
                teacher_c,
                model_bb,
                model_c,
                metrics_t,
                metrics_m,
                model_bbox_obj,
                layer_stats,
            )
            selected_img[page_type] = chosen_bb
            selection_debug[page_type] = {"source": chosen_source, **info}
    except Exception as error:
        selection_debug["fallback"] = str(error)

    site_bbox = img_norm_to_model_bbox(selected_img[SITE_PLAN], global_bbox)
    equip_bbox = img_norm_to_model_bbox(selected_img[EQUIPMENT_LAYOUT], global_bbox)
    specs = _to_page_specs(site_bbox, equip_bbox)

    report = {
        "viewport_aspect": float(viewport_aspect),
        "model_path": str(model_path),
        "teacher_debug": teacher_debug,
        "selected_img_boxes": selected_img,
        "selection_debug": selection_debug,
        "global_bbox": [global_bbox.minx, global_bbox.miny, global_bbox.maxx, global_bbox.maxy],
    }

    _RUN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RUN_REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return specs, report


def predict_view_boxes_from_dxf(source_dxf_bytes: bytes, model_path: str, viewport_aspect: float):
    specs, _ = infer_view_specs_from_dxf_bytes(source_dxf_bytes, model_path, viewport_aspect)
    return specs
