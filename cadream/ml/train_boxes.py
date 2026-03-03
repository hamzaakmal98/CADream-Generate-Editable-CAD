from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from model_boxes import TinyBoxRegressor, torch, nn


PAGE_KEYS = ["SITE_PLAN", "EQUIPMENT_LAYOUT"]
SITE_MIN_CONF = 0.7
EQUIP_MIN_CONF = 0.6


@dataclass
class SampleItem:
    case_id: str
    image: np.ndarray
    target: np.ndarray


class BoxesDataset(torch.utils.data.Dataset):
    def __init__(self, items: list[SampleItem]):
        self.items = items

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, str]:
        item = self.items[index]
        image = torch.from_numpy(item.image).float()
        target = torch.from_numpy(item.target).float()
        return image, target, item.case_id


def _load_png_4ch(path: Path) -> np.ndarray:
    from PIL import Image

    img = Image.open(path).convert("RGBA")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))
    return arr


def _flatten_target(teacher_boxes_img: dict[str, Any]) -> np.ndarray:
    values: list[float] = []
    for page_key in PAGE_KEYS:
        payload = teacher_boxes_img.get(page_key)
        if not isinstance(payload, dict):
            raise ValueError(f"Missing page key: {page_key}")
        bbox = payload.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError(f"Invalid bbox for: {page_key}")
        x1, y1, x2, y2 = [float(v) for v in bbox]
        values.extend([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
    return np.asarray(values, dtype=np.float32)


def _load_items(dataset_dir: Path) -> list[SampleItem]:
    items: list[SampleItem] = []
    for case_dir in sorted([path for path in dataset_dir.iterdir() if path.is_dir()]):
        teacher_path = case_dir / "teacher_boxes_img.json"
        image_path = case_dir / "input.png"

        if not teacher_path.exists() or not image_path.exists():
            continue

        payload = json.loads(teacher_path.read_text(encoding="utf-8"))

        site_conf = float((payload.get("SITE_PLAN") or {}).get("confidence", 0.0))
        equip_conf = float((payload.get("EQUIPMENT_LAYOUT") or {}).get("confidence", 0.0))
        if site_conf < SITE_MIN_CONF or equip_conf < EQUIP_MIN_CONF:
            continue

        item = SampleItem(
            case_id=case_dir.name,
            image=_load_png_4ch(image_path),
            target=_flatten_target(payload),
        )
        items.append(item)

    return items


def _split_items(items: list[SampleItem], val_ratio: float, seed: int) -> tuple[list[SampleItem], list[SampleItem]]:
    rng = random.Random(seed)
    shuffled = list(items)
    rng.shuffle(shuffled)

    if len(shuffled) <= 1:
        return shuffled, []

    val_count = max(1, int(round(len(shuffled) * val_ratio)))
    val_count = min(val_count, len(shuffled) - 1)
    return shuffled[val_count:], shuffled[:val_count]


def _coords_order_penalty(pred: torch.Tensor) -> torch.Tensor:
    x1 = pred[:, [0, 4]]
    y1 = pred[:, [1, 5]]
    x2 = pred[:, [2, 6]]
    y2 = pred[:, [3, 7]]
    return (torch.relu(x1 - x2).mean() + torch.relu(y1 - y2).mean())


def _box_iou(pred: torch.Tensor, target: torch.Tensor, offset: int) -> torch.Tensor:
    px1 = torch.minimum(pred[:, offset + 0], pred[:, offset + 2])
    py1 = torch.minimum(pred[:, offset + 1], pred[:, offset + 3])
    px2 = torch.maximum(pred[:, offset + 0], pred[:, offset + 2])
    py2 = torch.maximum(pred[:, offset + 1], pred[:, offset + 3])

    tx1 = torch.minimum(target[:, offset + 0], target[:, offset + 2])
    ty1 = torch.minimum(target[:, offset + 1], target[:, offset + 3])
    tx2 = torch.maximum(target[:, offset + 0], target[:, offset + 2])
    ty2 = torch.maximum(target[:, offset + 1], target[:, offset + 3])

    ix1 = torch.maximum(px1, tx1)
    iy1 = torch.maximum(py1, ty1)
    ix2 = torch.minimum(px2, tx2)
    iy2 = torch.minimum(py2, ty2)

    inter = torch.clamp(ix2 - ix1, min=0.0) * torch.clamp(iy2 - iy1, min=0.0)
    p_area = torch.clamp(px2 - px1, min=0.0) * torch.clamp(py2 - py1, min=0.0)
    t_area = torch.clamp(tx2 - tx1, min=0.0) * torch.clamp(ty2 - ty1, min=0.0)
    union = torch.clamp(p_area + t_area - inter, min=1e-8)
    return inter / union


def _anchor_coverage(pred_boxes: torch.Tensor, images: torch.Tensor) -> float:
    eq_channel = images[:, 1, :, :]
    n, h, w = eq_channel.shape
    coverages: list[float] = []

    for i in range(n):
        px1 = float(min(pred_boxes[i, 4], pred_boxes[i, 6]))
        py1 = float(min(pred_boxes[i, 5], pred_boxes[i, 7]))
        px2 = float(max(pred_boxes[i, 4], pred_boxes[i, 6]))
        py2 = float(max(pred_boxes[i, 5], pred_boxes[i, 7]))

        x1 = max(0, min(w - 1, int(round(px1 * (w - 1)))))
        x2 = max(0, min(w - 1, int(round(px2 * (w - 1)))))
        y1 = max(0, min(h - 1, int(round(py1 * (h - 1)))))
        y2 = max(0, min(h - 1, int(round(py2 * (h - 1)))))

        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        equipment_mask = eq_channel[i] > 0.2
        total = int(equipment_mask.sum().item())
        if total <= 0:
            continue

        inside = equipment_mask[y1 : y2 + 1, x1 : x2 + 1].sum().item()
        coverages.append(float(inside) / float(total))

    if not coverages:
        return 0.0
    return float(sum(coverages) / len(coverages))


def _evaluate(model: nn.Module, loader: torch.utils.data.DataLoader, device: torch.device) -> dict[str, float]:
    model.eval()
    iou_site: list[float] = []
    iou_equip: list[float] = []
    anchor_cov: list[float] = []

    with torch.no_grad():
        for images, targets, _ in loader:
            images = images.to(device)
            targets = targets.to(device)
            pred = model(images)

            iou_site.extend(_box_iou(pred, targets, offset=0).detach().cpu().tolist())
            iou_equip.extend(_box_iou(pred, targets, offset=4).detach().cpu().tolist())
            anchor_cov.append(_anchor_coverage(pred.detach().cpu(), images.detach().cpu()))

    return {
        "iou_site_plan": float(np.mean(iou_site)) if iou_site else 0.0,
        "iou_equipment_layout": float(np.mean(iou_equip)) if iou_equip else 0.0,
        "iou_mean": float(np.mean(iou_site + iou_equip)) if (iou_site or iou_equip) else 0.0,
        "anchor_coverage_equipment": float(np.mean(anchor_cov)) if anchor_cov else 0.0,
    }


def train(
    dataset_dir: Path,
    out_model: Path,
    epochs: int = 120,
    batch_size: int = 4,
    lr: float = 1e-3,
    val_ratio: float = 0.34,
    seed: int = 7,
) -> dict[str, Any]:
    items = _load_items(dataset_dir)
    if not items:
        raise RuntimeError("No training samples passed confidence filters for SITE_PLAN/EQUIPMENT_LAYOUT.")

    train_items, val_items = _split_items(items, val_ratio=val_ratio, seed=seed)

    train_loader = torch.utils.data.DataLoader(BoxesDataset(train_items), batch_size=min(batch_size, len(train_items)), shuffle=True)
    val_loader = torch.utils.data.DataLoader(BoxesDataset(val_items), batch_size=min(batch_size, max(1, len(val_items))), shuffle=False) if val_items else None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TinyBoxRegressor(in_channels=4).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    smooth_l1 = nn.SmoothL1Loss()

    last_loss = 0.0
    for _ in range(max(1, epochs)):
        model.train()
        losses: list[float] = []
        for images, targets, _ in train_loader:
            images = images.to(device)
            targets = targets.to(device)

            pred = model(images)
            loss_reg = smooth_l1(pred, targets)
            loss_order = _coords_order_penalty(pred)
            loss = loss_reg + 0.25 * loss_order

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))

        last_loss = float(np.mean(losses)) if losses else 0.0

    train_metrics = _evaluate(model, train_loader, device)
    val_metrics = _evaluate(model, val_loader, device) if val_loader is not None else {
        "iou_site_plan": 0.0,
        "iou_equipment_layout": 0.0,
        "iou_mean": 0.0,
        "anchor_coverage_equipment": 0.0,
    }

    out_model.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "page_keys": PAGE_KEYS,
            "input_channels": 4,
            "site_min_conf": SITE_MIN_CONF,
            "equip_min_conf": EQUIP_MIN_CONF,
        },
        out_model,
    )

    return {
        "samples_total": len(items),
        "samples_train": len(train_items),
        "samples_val": len(val_items),
        "loss_final": last_loss,
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "model_path": str(out_model),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train box regressor from teacher pseudo-labels.")
    parser.add_argument("--dataset", default="../../dataset", help="Dataset directory with case folders")
    parser.add_argument("--out-model", default="model.pt", help="Output model file")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val-ratio", type=float, default=0.34)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset).resolve()
    out_model = Path(args.out_model).resolve()

    metrics = train(
        dataset_dir=dataset_dir,
        out_model=out_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )

    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
