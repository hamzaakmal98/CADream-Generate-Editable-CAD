from __future__ import annotations

from ml.layer_stats import BBox


def model_bbox_to_img_norm(b: BBox, global_bbox: BBox) -> list[float]:
    """Returns [x1,y1,x2,y2] in [0,1] where y=0 top."""
    span_x = max(1e-9, global_bbox.maxx - global_bbox.minx)
    span_y = max(1e-9, global_bbox.maxy - global_bbox.miny)

    nx1 = (b.minx - global_bbox.minx) / span_x
    nx2 = (b.maxx - global_bbox.minx) / span_x
    ny1 = 1.0 - ((b.miny - global_bbox.miny) / span_y)
    ny2 = 1.0 - ((b.maxy - global_bbox.miny) / span_y)

    x1 = max(0.0, min(1.0, min(nx1, nx2)))
    x2 = max(0.0, min(1.0, max(nx1, nx2)))
    y1 = max(0.0, min(1.0, min(ny1, ny2)))
    y2 = max(0.0, min(1.0, max(ny1, ny2)))
    return [x1, y1, x2, y2]


def img_norm_to_model_bbox(bb: list[float], global_bbox: BBox) -> BBox:
    """Inverse mapping."""
    if len(bb) != 4:
        raise ValueError("bbox must have 4 values")

    x1, y1, x2, y2 = [float(v) for v in bb]
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    x2 = max(0.0, min(1.0, x2))
    y2 = max(0.0, min(1.0, y2))

    span_x = max(1e-9, global_bbox.maxx - global_bbox.minx)
    span_y = max(1e-9, global_bbox.maxy - global_bbox.miny)

    wx1 = global_bbox.minx + x1 * span_x
    wx2 = global_bbox.minx + x2 * span_x
    wy1 = global_bbox.miny + (1.0 - y1) * span_y
    wy2 = global_bbox.miny + (1.0 - y2) * span_y

    return BBox(min(wx1, wx2), min(wy1, wy2), max(wx1, wx2), max(wy1, wy2))
