from __future__ import annotations

import numpy as np

try:
    from .model import BoxRegressor, torch
except ImportError:
    from model import BoxRegressor, torch


def _cxcywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    arr = np.asarray(boxes, dtype=np.float32)
    cx = arr[..., 0]
    cy = arr[..., 1]
    w = np.clip(arr[..., 2], 1e-6, None)
    h = np.clip(arr[..., 3], 1e-6, None)
    x1 = cx - 0.5 * w
    y1 = cy - 0.5 * h
    x2 = cx + 0.5 * w
    y2 = cy + 0.5 * h
    out = np.stack([x1, y1, x2, y2], axis=-1)
    return np.clip(out, 0.0, 1.0)


def _quality_gate_score(box_xyxy: np.ndarray) -> float:
    x1, y1, x2, y2 = [float(v) for v in box_xyxy]
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    width = max(1e-6, x2 - x1)
    height = max(1e-6, y2 - y1)
    area = width * height
    area_center = 0.20
    area_score = max(0.0, 1.0 - min(1.0, abs(area - area_center) / area_center))
    edge_penalty = float(x1 <= 0.001 or y1 <= 0.001 or x2 >= 0.999 or y2 >= 0.999)
    tiny_penalty = float(width < 0.02 or height < 0.02)
    huge_penalty = float(area > 0.95)
    return area_score - 0.35 * edge_penalty - 0.75 * tiny_penalty - 0.50 * huge_penalty


def _apply_quality_gates(base_xyxy: np.ndarray, tta_xyxy: np.ndarray) -> np.ndarray:
    selected = np.array(base_xyxy, copy=True)
    for page_index in range(base_xyxy.shape[0]):
        base_box = base_xyxy[page_index]
        tta_box = tta_xyxy[page_index]
        base_score = _quality_gate_score(base_box)
        tta_score = _quality_gate_score(tta_box)
        selected[page_index] = tta_box if tta_score >= base_score else base_box
    return selected


def predict_boxes(model_path: str, image_tensor: np.ndarray) -> np.ndarray:
    """Predict normalized xyxy boxes from input image tensor [1,C,H,W] with horizontal-flip TTA and quality gates."""
    payload = torch.load(model_path, map_location="cpu")
    state = payload.get("model_state_dict") if isinstance(payload, dict) else None
    if not isinstance(state, dict):
        raise ValueError("Invalid model payload")

    input_channels = int(payload.get("input_channels", image_tensor.shape[1])) if isinstance(payload, dict) else int(image_tensor.shape[1])
    model = BoxRegressor(in_channels=input_channels)

    model.load_state_dict(state, strict=False)
    model.eval()

    with torch.no_grad():
        x = torch.from_numpy(image_tensor).float()
        pred_base, _ = model(x)
        pred_base = pred_base.cpu().numpy()

        x_flip = torch.flip(x, dims=[3])
        pred_flip, _ = model(x_flip)
        pred_flip = pred_flip.cpu().numpy()
        pred_flip[..., 0] = 1.0 - pred_flip[..., 0]

        pred_tta = 0.5 * (pred_base + pred_flip)

    base_xyxy = _cxcywh_to_xyxy(pred_base)
    tta_xyxy = _cxcywh_to_xyxy(pred_tta)
    selected_xyxy = _apply_quality_gates(base_xyxy[0], tta_xyxy[0])[None, ...]
    return selected_xyxy
