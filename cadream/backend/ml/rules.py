from __future__ import annotations

import re


SITE_BOUNDARY_LAYERS = [
    "unit area boundary", "property", "boundary", "parcel", "lot", "easement", "setback"
]

SITE_CONTEXT_LAYERS = [
    "base map", "road", "access", "topo", "contour", "ridge", "shading", "obstruction"
]

EQUIP_LAYERS = [
    "inverter", "module", "transformer", "combiner", "service panel", "switching station",
    "mounting structure", "equipment", "equip", "electrical", "power", "ac", "dc",
    "cable", "wire", "conduit", "trench", "ductbank", "bess", "battery", "container",
    "eqpt", "设备", "基础"
]

NOISE_LAYERS = [
    "drawing frame", "titleblock", "legend", "text", "annotation", "dimension", "dim",
    "pub_text", "pub_dim", "dim_coor", "dim_symb"
]

DOWNWEIGHT_LAYERS = ["shading", "obstruction", "0"]


def normalize(s: str) -> str:
    lowered = str(s).lower()
    lowered = re.sub(r"[_\-.]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered
