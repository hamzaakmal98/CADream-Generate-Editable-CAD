from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


SITE_PLAN = "SITE_PLAN"
EQUIPMENT_LAYOUT = "EQUIPMENT_LAYOUT"


@dataclass
class DatasetItem:
    case_id: str
    image: np.ndarray
    target: np.ndarray
    conf: np.ndarray
    presence: np.ndarray


def _load_image(path: Path) -> np.ndarray:
    from PIL import Image

    img = Image.open(path).convert("L")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr[None, :, :]


def _load_image_4ch(path: Path) -> np.ndarray:
    arr = np.load(path)
    if arr.ndim != 3 or arr.shape[0] != 4:
        raise ValueError(f"Expected input_4ch.npy shape [4,H,W], got {arr.shape}")
    return arr.astype(np.float32) / 255.0


def _clamp_conf(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return float(max(minimum, min(maximum, float(value))))


def _safe_read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _sorted_box(values: list[float]) -> list[float]:
    x1, y1, x2, y2 = [float(v) for v in values]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def load_items(dataset_dir: Path) -> list[DatasetItem]:
    items: list[DatasetItem] = []
    for case_dir in sorted([path for path in dataset_dir.iterdir() if path.is_dir()]):
        teacher_conf_payload = _safe_read_json(case_dir / "teacher_confidence.json")
        base_site_conf = _clamp_conf(float(teacher_conf_payload.get(SITE_PLAN, 1.0)))
        base_equip_conf = _clamp_conf(float(teacher_conf_payload.get(EQUIPMENT_LAYOUT, 1.0)))

        boxes_path = case_dir / "teacher_boxes_img.json"
        if not boxes_path.exists():
            continue

        boxes = json.loads(boxes_path.read_text(encoding="utf-8"))

        crops_root = case_dir / "crops"
        if crops_root.exists() and crops_root.is_dir():
            crop_dirs = [path for path in sorted(crops_root.iterdir()) if path.is_dir()]
            for crop_dir in crop_dirs:
                input_npy = crop_dir / "input.npy"
                if not input_npy.exists():
                    continue

                labels_payload = _safe_read_json(crop_dir / "labels.json").get("labels", {})
                presence_payload = _safe_read_json(crop_dir / "labels.json").get("presence", {})
                crop_meta_payload = _safe_read_json(crop_dir / "weights.json")
                conf_payload = crop_meta_payload.get("confidences", {}) if isinstance(crop_meta_payload, dict) else {}
                weights_payload = crop_meta_payload.get("weights", {}) if isinstance(crop_meta_payload, dict) else {}

                site_label = labels_payload.get(SITE_PLAN, [0.0, 0.0, 1.0, 1.0])
                equip_label = labels_payload.get(EQUIPMENT_LAYOUT, [0.0, 0.0, 1.0, 1.0])
                site_box = _sorted_box(list(site_label))
                equip_box = _sorted_box(list(equip_label))

                site_conf = conf_payload.get(SITE_PLAN, weights_payload.get(SITE_PLAN, base_site_conf))
                equip_conf = conf_payload.get(EQUIPMENT_LAYOUT, weights_payload.get(EQUIPMENT_LAYOUT, base_equip_conf))
                site_conf = _clamp_conf(site_conf)
                equip_conf = _clamp_conf(equip_conf)

                target = np.asarray([site_box, equip_box], dtype=np.float32)
                page_conf = np.asarray([site_conf, equip_conf], dtype=np.float32)
                page_presence = np.asarray(
                    [
                        float(presence_payload.get(SITE_PLAN, 1.0 if SITE_PLAN in labels_payload else 0.0)),
                        float(presence_payload.get(EQUIPMENT_LAYOUT, 1.0 if EQUIPMENT_LAYOUT in labels_payload else 0.0)),
                    ],
                    dtype=np.float32,
                )
                page_presence = np.clip(page_presence, 0.0, 1.0)
                image_tensor = _load_image_4ch(input_npy)
                items.append(
                    DatasetItem(
                        case_id=f"{case_dir.name}/crops/{crop_dir.name}",
                        image=image_tensor,
                        target=target,
                        conf=page_conf,
                        presence=page_presence,
                    )
                )
            continue

        image_4ch_path = case_dir / "input_4ch.npy"
        image_path = case_dir / "input.png"
        if not image_4ch_path.exists() and not image_path.exists():
            continue

        site_box = _sorted_box(list((boxes.get(SITE_PLAN) or {}).get("bbox", [0, 0, 1, 1])))
        equip_box = _sorted_box(list((boxes.get(EQUIPMENT_LAYOUT) or {}).get("bbox", [0, 0, 1, 1])))
        target = np.asarray([site_box, equip_box], dtype=np.float32)
        page_conf = np.asarray([_clamp_conf(base_site_conf), _clamp_conf(base_equip_conf)], dtype=np.float32)
        page_presence = np.asarray(
            [
                1.0 if isinstance((boxes.get(SITE_PLAN) or {}).get("bbox"), list) else 0.0,
                1.0 if isinstance((boxes.get(EQUIPMENT_LAYOUT) or {}).get("bbox"), list) else 0.0,
            ],
            dtype=np.float32,
        )
        image_tensor = _load_image_4ch(image_4ch_path) if image_4ch_path.exists() else _load_image(image_path)
        items.append(DatasetItem(case_id=case_dir.name, image=image_tensor, target=target, conf=page_conf, presence=page_presence))

    return items
