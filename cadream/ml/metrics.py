from __future__ import annotations

import numpy as np


def _as_box_tensor(boxes: np.ndarray) -> np.ndarray:
    arr = np.asarray(boxes)
    if arr.ndim == 3 and arr.shape[-2:] == (2, 4):
        return arr
    if arr.ndim == 2 and arr.shape[-1] == 8:
        return arr.reshape(arr.shape[0], 2, 4)
    if arr.ndim == 1 and arr.shape[0] == 8:
        return arr.reshape(1, 2, 4)
    raise ValueError(f"Expected boxes with shape [N,2,4] or [N,8], got {arr.shape}")


def sort_boxes(boxes: np.ndarray) -> np.ndarray:
    out = _as_box_tensor(boxes).copy()
    x1 = np.minimum(out[..., 0], out[..., 2])
    x2 = np.maximum(out[..., 0], out[..., 2])
    y1 = np.minimum(out[..., 1], out[..., 3])
    y2 = np.maximum(out[..., 1], out[..., 3])
    out[..., 0] = x1
    out[..., 1] = y1
    out[..., 2] = x2
    out[..., 3] = y2
    return out


def iou(pred: np.ndarray, target: np.ndarray) -> np.ndarray:
    pred = sort_boxes(pred)
    target = sort_boxes(target)

    ix1 = np.maximum(pred[..., 0], target[..., 0])
    iy1 = np.maximum(pred[..., 1], target[..., 1])
    ix2 = np.minimum(pred[..., 2], target[..., 2])
    iy2 = np.minimum(pred[..., 3], target[..., 3])

    inter = np.maximum(0.0, ix2 - ix1) * np.maximum(0.0, iy2 - iy1)
    p_area = np.maximum(0.0, pred[..., 2] - pred[..., 0]) * np.maximum(0.0, pred[..., 3] - pred[..., 1])
    t_area = np.maximum(0.0, target[..., 2] - target[..., 0]) * np.maximum(0.0, target[..., 3] - target[..., 1])
    union = np.maximum(1e-8, p_area + t_area - inter)
    return inter / union


def equipment_coverage(images: np.ndarray, pred_boxes: np.ndarray) -> float:
    pred_boxes = _as_box_tensor(pred_boxes)
    pred_boxes = sort_boxes(pred_boxes)
    n, _, h, w = images.shape
    coverages: list[float] = []

    equipment_channel_index = 1 if images.shape[1] > 1 else 0

    for index in range(n):
        x1, y1, x2, y2 = pred_boxes[index, 1, :]
        ix1 = max(0, min(w - 1, int(round(x1 * (w - 1)))))
        ix2 = max(0, min(w - 1, int(round(x2 * (w - 1)))))
        iy1 = max(0, min(h - 1, int(round(y1 * (h - 1)))))
        iy2 = max(0, min(h - 1, int(round(y2 * (h - 1)))))

        if ix2 < ix1:
            ix1, ix2 = ix2, ix1
        if iy2 < iy1:
            iy1, iy2 = iy2, iy1

        mask = images[index, equipment_channel_index] > 0.15
        total = float(mask.sum())
        if total <= 0:
            continue

        inside = float(mask[iy1 : iy2 + 1, ix1 : ix2 + 1].sum())
        coverages.append(inside / total)

    return float(np.mean(coverages)) if coverages else 0.0
