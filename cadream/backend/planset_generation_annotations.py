from __future__ import annotations

from math import hypot


def text_entity(*, layer: str, text: str, x: float, y: float, height: float = 2.2) -> dict:
    return {
        "kind": "text",
        "layer": layer,
        "data": {
            "text": text,
            "x": float(x),
            "y": float(y),
            "height": float(height),
        },
    }


def segment_length_label(
    *,
    layer: str,
    start: tuple[float, float],
    end: tuple[float, float],
    decimals: int = 1,
) -> dict:
    sx, sy = start
    ex, ey = end
    length = hypot(ex - sx, ey - sy)
    mx = (sx + ex) * 0.5
    my = (sy + ey) * 0.5
    return text_entity(layer=layer, text=f"{length:.{decimals}f}", x=mx, y=my)
