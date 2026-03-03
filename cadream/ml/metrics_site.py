from __future__ import annotations

import numpy as np


def bbox_to_mask(bb, height: int, width: int) -> np.ndarray:
	x1, y1, x2, y2 = [float(v) for v in bb]
	x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
	y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))

	x1_px = int(np.floor(x1 * width))
	x2_px = int(np.ceil(x2 * width))
	y1_px = int(np.floor(y1 * height))
	y2_px = int(np.ceil(y2 * height))

	x1_px = max(0, min(width, x1_px))
	x2_px = max(0, min(width, x2_px))
	y1_px = max(0, min(height, y1_px))
	y2_px = max(0, min(height, y2_px))

	mask = np.zeros((height, width), dtype=np.uint8)
	if x2_px <= x1_px or y2_px <= y1_px:
		return mask
	mask[y1_px:y2_px, x1_px:x2_px] = 1
	return mask


def boundary_coverage(boundary_bbox, pred_bbox) -> float:
	bx1, by1, bx2, by2 = [float(v) for v in boundary_bbox]
	px1, py1, px2, py2 = [float(v) for v in pred_bbox]

	bx1, bx2 = sorted((bx1, bx2))
	by1, by2 = sorted((by1, by2))
	px1, px2 = sorted((px1, px2))
	py1, py2 = sorted((py1, py2))

	inter_x1 = max(bx1, px1)
	inter_y1 = max(by1, py1)
	inter_x2 = min(bx2, px2)
	inter_y2 = min(by2, py2)

	inter_w = max(0.0, inter_x2 - inter_x1)
	inter_h = max(0.0, inter_y2 - inter_y1)
	inter_area = inter_w * inter_h

	boundary_area = max(1e-9, (bx2 - bx1) * (by2 - by1))
	value = inter_area / boundary_area
	return float(max(0.0, min(1.0, value)))


def channel_coverage_ratio(channel: np.ndarray, mask: np.ndarray) -> float:
	ch = np.asarray(channel, dtype=np.float32)
	mk = np.asarray(mask, dtype=np.float32)
	numerator = float(np.sum(ch * mk))
	denominator = float(np.sum(ch)) + 1e-9
	return float(numerator / denominator)


def channel_inside_ratio(channel: np.ndarray, mask: np.ndarray) -> float:
	ch = np.asarray(channel, dtype=np.float32)
	mk = np.asarray(mask, dtype=np.float32)
	numerator = float(np.sum(ch * mk))
	denominator = float(np.sum(mk)) + 1e-9
	return float(numerator / denominator)
