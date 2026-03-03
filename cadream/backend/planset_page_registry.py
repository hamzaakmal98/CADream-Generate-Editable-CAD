from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path(__file__).resolve().parent / "config" / "planset_page_registry.json"


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid planset page registry format")
    return data


def get_page_registry_entries() -> list[dict[str, Any]]:
    data = _load_registry()
    pages = data.get("pages")
    if not isinstance(pages, list):
        return []

    normalized: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_number = page.get("page_number")
        mode = page.get("mode")
        if not isinstance(page_number, int) or page_number <= 0:
            continue
        if not isinstance(mode, str) or not mode.strip():
            continue
        normalized.append(page)

    normalized.sort(key=lambda item: int(item["page_number"]))
    return normalized


def get_page_registry_map() -> dict[int, dict[str, Any]]:
    return {int(entry["page_number"]): entry for entry in get_page_registry_entries()}


def get_template_source_path() -> str:
    data = _load_registry()
    value = data.get("template_source")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "sample-files/Template_Project.pdf"


def get_mode_page_numbers(mode: str) -> list[int]:
    target = (mode or "").strip()
    if not target:
        return []
    out: list[int] = []
    for entry in get_page_registry_entries():
        if entry.get("mode") == target:
            out.append(int(entry["page_number"]))
    return out
