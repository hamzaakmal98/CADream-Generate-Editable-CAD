from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_VERSION = "page-view-spec-v1"
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "page-view-spec-v1.schema.json"
_PAGE_VIEW_SPEC_VALIDATOR = Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Bounds2D:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        if self.max_x <= self.min_x:
            raise ValueError("Bounds2D.max_x must be greater than min_x")
        if self.max_y <= self.min_y:
            raise ValueError("Bounds2D.max_y must be greater than min_y")

    def to_dict(self) -> dict[str, list[float]]:
        return {
            "min": [self.min_x, self.min_y],
            "max": [self.max_x, self.max_y],
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "Bounds2D":
        if not isinstance(payload, dict):
            raise ValueError("view_bounds must be an object")
        raw_min = payload.get("min")
        raw_max = payload.get("max")
        if (
            not isinstance(raw_min, list)
            or not isinstance(raw_max, list)
            or len(raw_min) != 2
            or len(raw_max) != 2
        ):
            raise ValueError("view_bounds.min/max must be [x, y]")
        return cls(
            min_x=float(raw_min[0]),
            min_y=float(raw_min[1]),
            max_x=float(raw_max[0]),
            max_y=float(raw_max[1]),
        )


@dataclass(frozen=True)
class SheetSpec:
    width: float
    height: float
    units: str

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("sheet.width must be > 0")
        if self.height <= 0:
            raise ValueError("sheet.height must be > 0")
        if not self.units.strip():
            raise ValueError("sheet.units must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "SheetSpec":
        if not isinstance(payload, dict):
            raise ValueError("sheet must be an object")
        return cls(
            width=float(payload.get("width")),
            height=float(payload.get("height")),
            units=str(payload.get("units") or "").strip(),
        )


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    title_block_block_name: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("template.id must be a non-empty string")
        if not self.title_block_block_name.strip():
            raise ValueError("template.title_block_block_name must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title_block_block_name": self.title_block_block_name,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "TemplateSpec":
        if not isinstance(payload, dict):
            raise ValueError("template must be an object")
        return cls(
            id=str(payload.get("id") or "").strip(),
            title_block_block_name=str(payload.get("title_block_block_name") or "").strip(),
        )


@dataclass(frozen=True)
class LayerSpec:
    freeze: tuple[str, ...] = ()
    include: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        payload: dict[str, list[str]] = {}
        if self.freeze:
            payload["freeze"] = list(self.freeze)
        if self.include:
            payload["include"] = list(self.include)
        return payload

    @classmethod
    def from_dict(cls, payload: Any) -> "LayerSpec":
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise ValueError("layers must be an object when provided")

        raw_freeze = payload.get("freeze")
        raw_include = payload.get("include")

        freeze = tuple(str(item) for item in raw_freeze) if isinstance(raw_freeze, list) else ()
        include = tuple(str(item) for item in raw_include) if isinstance(raw_include, list) else ()
        return cls(freeze=freeze, include=include)


@dataclass(frozen=True)
class PageViewSpec:
    page_number: int
    page_name: str
    view_bounds: Bounds2D
    sheet: SheetSpec
    viewport_rect: tuple[float, float, float, float]
    template: TemplateSpec
    layers: LayerSpec = LayerSpec()
    overlays: dict[str, Any] | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        if self.page_number <= 0:
            raise ValueError("page_number must be >= 1")
        if not self.page_name.strip():
            raise ValueError("page_name must be a non-empty string")

        x1, y1, x2, y2 = self.viewport_rect
        if x2 <= x1:
            raise ValueError("viewport_rect x2 must be greater than x1")
        if y2 <= y1:
            raise ValueError("viewport_rect y2 must be greater than y1")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "page_number": self.page_number,
            "page_name": self.page_name,
            "view_bounds": self.view_bounds.to_dict(),
            "sheet": self.sheet.to_dict(),
            "viewport_rect": list(self.viewport_rect),
            "template": self.template.to_dict(),
        }
        layer_payload = self.layers.to_dict()
        if layer_payload:
            payload["layers"] = layer_payload
        if self.overlays is not None:
            payload["overlays"] = self.overlays
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PageViewSpec":
        validate_page_view_spec_payload(payload)

        raw_viewport = payload.get("viewport_rect")
        if not isinstance(raw_viewport, list) or len(raw_viewport) != 4:
            raise ValueError("viewport_rect must be [x1, y1, x2, y2]")

        overlays = payload.get("overlays")
        if overlays is not None and not isinstance(overlays, dict):
            raise ValueError("overlays must be an object or null")

        return cls(
            schema_version=str(payload.get("schema_version") or ""),
            page_number=int(payload.get("page_number")),
            page_name=str(payload.get("page_name") or "").strip(),
            view_bounds=Bounds2D.from_dict(payload.get("view_bounds")),
            sheet=SheetSpec.from_dict(payload.get("sheet")),
            viewport_rect=(
                float(raw_viewport[0]),
                float(raw_viewport[1]),
                float(raw_viewport[2]),
                float(raw_viewport[3]),
            ),
            template=TemplateSpec.from_dict(payload.get("template")),
            layers=LayerSpec.from_dict(payload.get("layers")),
            overlays=overlays,
        )


def validate_page_view_spec_payload(payload: dict[str, Any]) -> None:
    errors = sorted(_PAGE_VIEW_SPEC_VALIDATOR.iter_errors(payload), key=lambda item: list(item.path))
    if not errors:
        return

    parts: list[str] = []
    for error in errors:
        path = ".".join(str(item) for item in error.path) if error.path else "page_view_spec"
        parts.append(f"{path}: {error.message}")
    raise ValueError("; ".join(parts))


def validate_page_view_specs_payload(payload: Any) -> None:
    if not isinstance(payload, list):
        raise ValueError("page_view_specs must be an array")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"page_view_specs[{index}] must be an object")
        validate_page_view_spec_payload(item)


def parse_page_view_specs(payload: Any) -> list[PageViewSpec]:
    validate_page_view_specs_payload(payload)
    specs: list[PageViewSpec] = []
    assert isinstance(payload, list)
    for item in payload:
        assert isinstance(item, dict)
        specs.append(PageViewSpec.from_dict(item))
    return specs
