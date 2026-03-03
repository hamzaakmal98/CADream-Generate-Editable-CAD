from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import ezdxf

from cad_parser import dxf_to_render_json
from page_view_spec import Bounds2D, LayerSpec, PageViewSpec, SheetSpec, TemplateSpec
from planset_generation_geometry import expand_bounds


@dataclass(frozen=True)
class HeuristicViewSpecConfig:
    include_overall_page: bool = True
    start_page_number: int = 1
    grid_rows: int = 2
    grid_cols: int = 2
    max_grid_pages: int = 4
    use_density_ranking: bool = False
    density_quantile_low: float = 0.02
    density_quantile_high: float = 0.98
    density_min_points: int = 20
    overall_pad_ratio: float = 0.08
    overall_min_pad: float = 5.0
    tile_pad_ratio: float = 0.04
    tile_min_pad: float = 2.0
    sheet_width: float = 420.0
    sheet_height: float = 297.0
    sheet_units: str = "millimeter"
    viewport_rect: tuple[float, float, float, float] = (24.0, 86.0, 312.0, 266.0)
    template_id: str = "template-v1"
    title_block_block_name: str = "CADREAM_TITLEBLOCK_V1"


def _bounds_from_render_payload(render_payload: dict[str, Any]) -> Bounds2D:
    bounds = render_payload.get("bounds") if isinstance(render_payload, dict) else None
    if not isinstance(bounds, dict):
        raise ValueError("Render payload has no bounds")

    raw_min = bounds.get("min")
    raw_max = bounds.get("max")
    if (
        not isinstance(raw_min, list)
        or not isinstance(raw_max, list)
        or len(raw_min) < 2
        or len(raw_max) < 2
    ):
        raise ValueError("Render payload bounds must include min/max XY pairs")

    return Bounds2D(
        min_x=float(raw_min[0]),
        min_y=float(raw_min[1]),
        max_x=float(raw_max[0]),
        max_y=float(raw_max[1]),
    )


def _bounds_from_doc_header(doc: ezdxf.document.Drawing) -> Bounds2D | None:
    try:
        ext_min = doc.header.get("$EXTMIN")
        ext_max = doc.header.get("$EXTMAX")
        if ext_min is None or ext_max is None:
            return None

        min_x = float(ext_min[0])
        min_y = float(ext_min[1])
        max_x = float(ext_max[0])
        max_y = float(ext_max[1])

        values = (min_x, min_y, max_x, max_y)
        if not all(math.isfinite(value) for value in values):
            return None
        if max_x <= min_x or max_y <= min_y:
            return None

        return Bounds2D(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)
    except Exception:
        return None


def _expanded(bounds: Bounds2D, *, pad_ratio: float, min_pad: float) -> Bounds2D:
    out = expand_bounds(
        (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y),
        pad_ratio=pad_ratio,
        min_pad=min_pad,
    )
    return Bounds2D(min_x=out[0], min_y=out[1], max_x=out[2], max_y=out[3])


def _tile_bounds(base: Bounds2D, rows: int, cols: int) -> list[Bounds2D]:
    width = base.max_x - base.min_x
    height = base.max_y - base.min_y
    cell_w = width / cols
    cell_h = height / rows

    tiles: list[Bounds2D] = []
    for row_index in range(rows):
        for col_index in range(cols):
            min_x = base.min_x + col_index * cell_w
            max_x = base.min_x + (col_index + 1) * cell_w
            min_y = base.min_y + row_index * cell_h
            max_y = base.min_y + (row_index + 1) * cell_h
            tiles.append(Bounds2D(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y))
    return tiles


def _extract_density_points(render_payload: dict[str, Any]) -> list[tuple[float, float]]:
    entities = render_payload.get("entities") if isinstance(render_payload, dict) else None
    if not isinstance(entities, list):
        return []

    insert_points: list[tuple[float, float]] = []
    fallback_points: list[tuple[float, float]] = []

    for entity in entities:
        if not isinstance(entity, dict):
            continue

        entity_type = entity.get("type")
        if entity_type == "INSERT":
            pos = entity.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                insert_points.append((float(pos[0]), float(pos[1])))
            continue

        if entity_type == "LINE":
            p1 = entity.get("p1")
            p2 = entity.get("p2")
            if isinstance(p1, list) and len(p1) >= 2 and isinstance(p2, list) and len(p2) >= 2:
                fallback_points.append(((float(p1[0]) + float(p2[0])) * 0.5, (float(p1[1]) + float(p2[1])) * 0.5))
            continue

        if entity_type == "LWPOLYLINE":
            points = entity.get("points")
            if isinstance(points, list) and points:
                total_x = 0.0
                total_y = 0.0
                count = 0
                for point in points:
                    if isinstance(point, list) and len(point) >= 2:
                        total_x += float(point[0])
                        total_y += float(point[1])
                        count += 1
                if count > 0:
                    fallback_points.append((total_x / count, total_y / count))
            continue

        if entity_type in {"CIRCLE", "ARC"}:
            center = entity.get("center")
            if isinstance(center, list) and len(center) >= 2:
                fallback_points.append((float(center[0]), float(center[1])))
            continue

        if entity_type in {"TEXT", "MTEXT"}:
            pos = entity.get("pos")
            if isinstance(pos, list) and len(pos) >= 2:
                fallback_points.append((float(pos[0]), float(pos[1])))

    if insert_points:
        return insert_points
    return fallback_points


def _point_in_bounds(x: float, y: float, bounds: Bounds2D) -> bool:
    return bounds.min_x <= x <= bounds.max_x and bounds.min_y <= y <= bounds.max_y


def _rank_tiles_by_density(tiles: list[Bounds2D], points: list[tuple[float, float]]) -> list[int]:
    if not tiles:
        return []
    if not points:
        return list(range(len(tiles)))

    scored_indices: list[tuple[int, int]] = []
    for index, tile in enumerate(tiles):
        score = 0
        for x, y in points:
            if _point_in_bounds(x, y, tile):
                score += 1
        scored_indices.append((index, score))

    scored_indices.sort(key=lambda item: (-item[1], item[0]))
    return [index for index, _score in scored_indices]


def _rank_tiles_by_density_with_scores(
    tiles: list[Bounds2D], points: list[tuple[float, float]]
) -> list[tuple[int, int]]:
    if not tiles:
        return []
    if not points:
        return [(index, 0) for index in range(len(tiles))]

    scored_indices: list[tuple[int, int]] = []
    for index, tile in enumerate(tiles):
        score = 0
        for x, y in points:
            if _point_in_bounds(x, y, tile):
                score += 1
        scored_indices.append((index, score))

    scored_indices.sort(key=lambda item: (-item[1], item[0]))
    return scored_indices


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)
    clamped_q = min(1.0, max(0.0, q))
    index = (len(sorted_values) - 1) * clamped_q
    lo = int(math.floor(index))
    hi = int(math.ceil(index))
    if lo == hi:
        return sorted_values[lo]
    t = index - lo
    return sorted_values[lo] * (1.0 - t) + sorted_values[hi] * t


def _shortest_interval(values: list[float], fraction: float) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    window = max(2, min(n, int(math.floor(n * max(0.1, min(1.0, fraction))))))

    best_start = 0
    best_end = window - 1
    best_width = sorted_values[best_end] - sorted_values[best_start]

    for start in range(1, n - window + 1):
        end = start + window - 1
        width = sorted_values[end] - sorted_values[start]
        if width < best_width:
            best_start = start
            best_end = end
            best_width = width

    return sorted_values[best_start], sorted_values[best_end]


def _robust_bounds_from_density_points(
    points: list[tuple[float, float]],
    base_bounds: Bounds2D,
    cfg: HeuristicViewSpecConfig,
) -> Bounds2D | None:
    if len(points) < cfg.density_min_points:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    q_min_x = _quantile(xs, cfg.density_quantile_low)
    q_max_x = _quantile(xs, cfg.density_quantile_high)
    q_min_y = _quantile(ys, cfg.density_quantile_low)
    q_max_y = _quantile(ys, cfg.density_quantile_high)

    core_min_x, core_max_x = _shortest_interval(xs, 0.85)
    core_min_y, core_max_y = _shortest_interval(ys, 0.85)

    q_width = q_max_x - q_min_x
    q_height = q_max_y - q_min_y
    core_width = core_max_x - core_min_x
    core_height = core_max_y - core_min_y

    if core_width > 0 and core_height > 0 and (core_width * core_height) < (q_width * q_height) * 0.9:
        min_x, max_x = core_min_x, core_max_x
        min_y, max_y = core_min_y, core_max_y
    else:
        min_x, max_x = q_min_x, q_max_x
        min_y, max_y = q_min_y, q_max_y

    width = max_x - min_x
    height = max_y - min_y
    base_width = base_bounds.max_x - base_bounds.min_x
    base_height = base_bounds.max_y - base_bounds.min_y

    if width <= 0 or height <= 0:
        return None
    if base_width <= 0 or base_height <= 0:
        return None

    return Bounds2D(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def _shrink_bounds(bounds: Bounds2D, factor: float) -> Bounds2D:
    clamped = min(1.0, max(0.2, factor))
    cx = (bounds.min_x + bounds.max_x) * 0.5
    cy = (bounds.min_y + bounds.max_y) * 0.5
    half_w = (bounds.max_x - bounds.min_x) * 0.5 * clamped
    half_h = (bounds.max_y - bounds.min_y) * 0.5 * clamped
    return Bounds2D(min_x=cx - half_w, min_y=cy - half_h, max_x=cx + half_w, max_y=cy + half_h)


def _build_page_spec(
    *,
    page_number: int,
    page_name: str,
    view_bounds: Bounds2D,
    config: HeuristicViewSpecConfig,
) -> PageViewSpec:
    return PageViewSpec(
        page_number=page_number,
        page_name=page_name,
        view_bounds=view_bounds,
        sheet=SheetSpec(width=config.sheet_width, height=config.sheet_height, units=config.sheet_units),
        viewport_rect=config.viewport_rect,
        template=TemplateSpec(id=config.template_id, title_block_block_name=config.title_block_block_name),
        layers=LayerSpec(),
        overlays=None,
    )


def make_view_specs_from_render_payload(
    render_payload: dict[str, Any],
    *,
    config: HeuristicViewSpecConfig | None = None,
) -> list[PageViewSpec]:
    cfg = config or HeuristicViewSpecConfig()
    if cfg.grid_rows <= 0 or cfg.grid_cols <= 0:
        raise ValueError("grid_rows and grid_cols must be positive")
    if cfg.max_grid_pages <= 0:
        raise ValueError("max_grid_pages must be positive")

    base_bounds = _bounds_from_render_payload(render_payload)
    overall_seed = base_bounds
    if cfg.use_density_ranking:
        density_points = _extract_density_points(render_payload)
        robust_bounds = _robust_bounds_from_density_points(density_points, base_bounds, cfg)
        if robust_bounds is not None:
            overall_seed = robust_bounds

    overall_bounds = _expanded(overall_seed, pad_ratio=cfg.overall_pad_ratio, min_pad=cfg.overall_min_pad)

    specs: list[PageViewSpec] = []
    next_page = cfg.start_page_number

    if cfg.include_overall_page:
        specs.append(
            _build_page_spec(
                page_number=next_page,
                page_name="Overall Site View",
                view_bounds=overall_bounds,
                config=cfg,
            )
        )
        next_page += 1

    tile_candidates = _tile_bounds(overall_bounds, rows=cfg.grid_rows, cols=cfg.grid_cols)
    tile_count = min(len(tile_candidates), cfg.max_grid_pages)

    if cfg.use_density_ranking:
        density_points = _extract_density_points(render_payload)
        ranked_tile_scores = _rank_tiles_by_density_with_scores(tile_candidates, density_points)
        nonzero = [index for index, score in ranked_tile_scores if score > 0]
        selected_tile_indices = nonzero[:tile_count]

        if len(selected_tile_indices) < tile_count:
            fallback_indices = [index for index, _score in ranked_tile_scores] or list(range(len(tile_candidates)))
            cursor = 0
            while len(selected_tile_indices) < tile_count and fallback_indices:
                selected_tile_indices.append(fallback_indices[cursor % len(fallback_indices)])
                cursor += 1
    else:
        selected_tile_indices = list(range(tile_count))

    for selection_index, tile_index in enumerate(selected_tile_indices):
        row_index = tile_index // cfg.grid_cols
        col_index = tile_index % cfg.grid_cols
        tile_bounds = tile_candidates[tile_index]

        duplicate_count = selected_tile_indices[:selection_index].count(tile_index)
        if duplicate_count > 0:
            shrink_factor = max(0.45, 1.0 - duplicate_count * 0.15)
            tile_bounds = _shrink_bounds(tile_bounds, shrink_factor)

        padded_tile = _expanded(
            tile_bounds,
            pad_ratio=cfg.tile_pad_ratio,
            min_pad=cfg.tile_min_pad,
        )
        specs.append(
            _build_page_spec(
                page_number=next_page,
                page_name=f"Detail Grid R{row_index + 1}C{col_index + 1}",
                view_bounds=padded_tile,
                config=cfg,
            )
        )
        next_page += 1

    return specs


def make_view_specs_from_source(
    source: dict[str, Any] | ezdxf.document.Drawing,
    *,
    config: HeuristicViewSpecConfig | None = None,
    max_entities: int = 50000,
) -> list[PageViewSpec]:
    if isinstance(source, dict):
        render_payload = source
        return make_view_specs_from_render_payload(render_payload, config=config)

    render_payload = dxf_to_render_json(source, max_entities=max_entities)
    try:
        return make_view_specs_from_render_payload(render_payload, config=config)
    except ValueError as error:
        if "no bounds" not in str(error).lower():
            raise

    fallback_bounds = _bounds_from_doc_header(source)
    if fallback_bounds is None:
        fallback_bounds = Bounds2D(min_x=-50.0, min_y=-50.0, max_x=50.0, max_y=50.0)

    fallback_payload = {
        "bounds": {
            "min": [fallback_bounds.min_x, fallback_bounds.min_y],
            "max": [fallback_bounds.max_x, fallback_bounds.max_y],
        }
    }
    return make_view_specs_from_render_payload(fallback_payload, config=config)
