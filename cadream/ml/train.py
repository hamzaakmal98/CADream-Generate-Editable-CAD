from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

from dataset import load_items
from metrics import equipment_coverage, iou, sort_boxes
from model import BoxRegressor, nn, torch


def _split_indices(count: int, val_frac: float, seed: int) -> tuple[list[int], list[int]]:
    rng = random.Random(seed)
    idx = list(range(count))
    rng.shuffle(idx)
    if count <= 1:
        return idx, []
    val_n = max(1, int(round(count * val_frac)))
    val_n = min(val_n, count - 1)
    return idx[val_n:], idx[:val_n]


def _batch_from_items(items, indices):
    images = np.stack([items[i].image for i in indices], axis=0)
    targets = np.stack([items[i].target for i in indices], axis=0)
    presence = np.stack([items[i].presence for i in indices], axis=0)
    return images, targets, presence


def _xyxy_to_cxcywh_torch(boxes: torch.Tensor) -> torch.Tensor:
    x1 = torch.minimum(boxes[..., 0], boxes[..., 2])
    y1 = torch.minimum(boxes[..., 1], boxes[..., 3])
    x2 = torch.maximum(boxes[..., 0], boxes[..., 2])
    y2 = torch.maximum(boxes[..., 1], boxes[..., 3])
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    w = torch.clamp(x2 - x1, min=1e-6)
    h = torch.clamp(y2 - y1, min=1e-6)
    return torch.stack([cx, cy, w, h], dim=-1)


def _cxcywh_to_xyxy_torch(boxes: torch.Tensor) -> torch.Tensor:
    cx = boxes[..., 0]
    cy = boxes[..., 1]
    w = torch.clamp(boxes[..., 2], min=1e-6)
    h = torch.clamp(boxes[..., 3], min=1e-6)
    x1 = cx - 0.5 * w
    y1 = cy - 0.5 * h
    x2 = cx + 0.5 * w
    y2 = cy + 0.5 * h
    out = torch.stack([x1, y1, x2, y2], dim=-1)
    return torch.clamp(out, 0.0, 1.0)


def _cxcywh_to_xyxy_np(boxes: np.ndarray) -> np.ndarray:
    cx = boxes[..., 0]
    cy = boxes[..., 1]
    w = np.clip(boxes[..., 2], 1e-6, None)
    h = np.clip(boxes[..., 3], 1e-6, None)
    x1 = cx - 0.5 * w
    y1 = cy - 0.5 * h
    x2 = cx + 0.5 * w
    y2 = cy + 0.5 * h
    out = np.stack([x1, y1, x2, y2], axis=-1)
    return np.clip(out, 0.0, 1.0)


def _coords_penalty(pred_cxcywh: torch.Tensor) -> torch.Tensor:
    widths = pred_cxcywh[..., 2]
    heights = pred_cxcywh[..., 3]
    min_size = 0.02
    return torch.relu(min_size - widths).mean() + torch.relu(min_size - heights).mean()


def _sample_confidence(items, indices: list[int]) -> np.ndarray:
    values: list[float] = []
    for index in indices:
        conf = items[index].conf
        site = float(conf[0]) if conf.size > 0 else 0.0
        equip = float(conf[1]) if conf.size > 1 else site
        values.append(max(1e-6, 0.5 * (site + equip)))
    return np.asarray(values, dtype=np.float32)


def _soft_box_mask(h: int, w: int, box: torch.Tensor, slope: float = 30.0) -> torch.Tensor:
    x1 = torch.minimum(box[:, 0], box[:, 2]).view(-1, 1, 1)
    y1 = torch.minimum(box[:, 1], box[:, 3]).view(-1, 1, 1)
    x2 = torch.maximum(box[:, 0], box[:, 2]).view(-1, 1, 1)
    y2 = torch.maximum(box[:, 1], box[:, 3]).view(-1, 1, 1)

    ys = torch.linspace(0.0, 1.0, steps=h, device=box.device, dtype=box.dtype).view(1, h, 1)
    xs = torch.linspace(0.0, 1.0, steps=w, device=box.device, dtype=box.dtype).view(1, 1, w)

    left = torch.sigmoid(slope * (xs - x1))
    right = torch.sigmoid(slope * (x2 - xs))
    top = torch.sigmoid(slope * (ys - y1))
    bottom = torch.sigmoid(slope * (y2 - ys))
    return left * right * top * bottom


def _equipment_aux_losses(images: torch.Tensor, pred: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    bsz, channels, height, width = images.shape
    equipment_channel = images[:, 1] if channels > 1 else images[:, 0]
    noise_channel = images[:, 3] if channels > 3 else torch.zeros_like(equipment_channel)

    equip_box = pred[:, 1, :]
    mask = _soft_box_mask(height, width, equip_box)

    equip_total = equipment_channel.sum(dim=(1, 2)) + 1e-6
    equip_inside = (equipment_channel * mask).sum(dim=(1, 2))
    equip_outside = (equipment_channel * (1.0 - mask)).sum(dim=(1, 2))

    inside_ratio = equip_inside / equip_total
    outside_ratio = equip_outside / equip_total
    coverage_loss = (1.0 - inside_ratio) + 0.5 * outside_ratio

    noise_total = noise_channel.sum(dim=(1, 2)) + 1e-6
    noise_inside = (noise_channel * mask).sum(dim=(1, 2))
    noise_loss = noise_inside / noise_total

    return coverage_loss, noise_loss


def _loss_weight_schedule(epoch_index: int) -> tuple[float, float, float]:
    epoch_num = int(epoch_index) + 1
    if epoch_num <= 40:
        return 0.5, 0.1, 0.05
    return 0.3, 0.2, 0.1


def train(
    dataset_dir: Path,
    out_model: Path,
    epochs: int,
    batch: int,
    lr: float,
    seed: int,
    *,
    weight_presence: float = 0.15,
    curriculum_high_q: float = 0.85,
    curriculum_low_q: float = 0.20,
) -> dict:
    items = load_items(dataset_dir)
    if not items:
        raise RuntimeError("No samples passed confidence thresholds")

    train_idx, val_idx = _split_indices(len(items), val_frac=0.3, seed=seed)
    input_channels = int(items[0].image.shape[0])
    model = BoxRegressor(in_channels=input_channels)
    optim = torch.optim.Adam(model.parameters(), lr=lr)
    smooth_l1 = nn.SmoothL1Loss(reduction="none")
    bce_logits = nn.BCEWithLogitsLoss(reduction="none")

    logs: list[dict] = []

    for epoch in range(max(1, epochs)):
        weight_coords, weight_equip_coverage, weight_noise_suppression = _loss_weight_schedule(epoch)
        rng = np.random.default_rng(seed + epoch)
        epoch_indices = list(train_idx)
        rng.shuffle(epoch_indices)
        num_samples_seen = len(epoch_indices)
        losses: list[float] = []
        reg_losses: list[float] = []
        cov_losses: list[float] = []
        noise_losses: list[float] = []
        presence_losses: list[float] = []
        epoch_w_site: list[float] = []
        epoch_w_equip: list[float] = []

        for start in range(0, len(epoch_indices), max(1, batch)):
            batch_idx = epoch_indices[start : start + max(1, batch)]
            images_np, targets_np, presence_np = _batch_from_items(items, batch_idx)
            images = torch.from_numpy(images_np).float()
            targets = torch.from_numpy(targets_np).float()
            presence_targets = torch.from_numpy(presence_np).float()
            targets_cxcywh = _xyxy_to_cxcywh_torch(targets)
            page_conf = torch.tensor(
                [
                    [
                        max(0.0, float(items[index].conf[0])),
                        max(0.0, float(items[index].conf[1])),
                    ]
                    for index in batch_idx
                ],
                dtype=images.dtype,
            )
            w_site = torch.clamp(page_conf[:, 0], min=0.2, max=1.0)
            w_equip = torch.clamp(page_conf[:, 1], min=0.2, max=1.0)
            epoch_w_site.extend([float(value) for value in w_site.detach().cpu().numpy().tolist()])
            epoch_w_equip.extend([float(value) for value in w_equip.detach().cpu().numpy().tolist()])

            pred_cxcywh, pred_presence_logits = model(images)
            pred_xyxy = _cxcywh_to_xyxy_torch(pred_cxcywh)
            reg_per_page = smooth_l1(pred_cxcywh, targets_cxcywh).mean(dim=2)
            site_bbox_loss = reg_per_page[:, 0] * w_site
            equip_bbox_loss = reg_per_page[:, 1] * w_equip
            reg_tensor = site_bbox_loss + equip_bbox_loss
            presence_per_page = bce_logits(pred_presence_logits, presence_targets)
            presence_tensor = 0.5 * (presence_per_page[:, 0] * w_site + presence_per_page[:, 1] * w_equip)
            coverage_loss, noise_loss = _equipment_aux_losses(images, pred_xyxy)

            coverage_loss = coverage_loss * w_equip
            noise_loss = noise_loss * w_equip

            weighted_reg = reg_tensor.mean()
            weighted_presence = presence_tensor.mean()
            weighted_cov = coverage_loss.mean()
            weighted_noise = noise_loss.mean()

            loss = (
                weighted_reg
                + weight_coords * _coords_penalty(pred_cxcywh)
                + float(weight_presence) * weighted_presence
                + weight_equip_coverage * weighted_cov
                + weight_noise_suppression * weighted_noise
            )

            optim.zero_grad()
            loss.backward()
            optim.step()
            losses.append(float(loss.item()))
            reg_losses.append(float(weighted_reg.item()))
            presence_losses.append(float(weighted_presence.item()))
            cov_losses.append(float(weighted_cov.item()))
            noise_losses.append(float(weighted_noise.item()))

        train_images, train_targets, _ = _batch_from_items(items, train_idx)
        train_pred, _ = model(torch.from_numpy(train_images).float())
        train_pred = train_pred.detach().cpu().numpy()
        train_pred = _cxcywh_to_xyxy_np(train_pred)
        train_pred = sort_boxes(train_pred)
        train_targets = sort_boxes(train_targets)

        train_iou = iou(train_pred, train_targets)
        train_area = (train_pred[..., 2] - train_pred[..., 0]) * (train_pred[..., 3] - train_pred[..., 1])

        entry = {
            "epoch": epoch + 1,
            "loss": float(np.mean(losses)) if losses else 0.0,
            "loss_reg": float(np.mean(reg_losses)) if reg_losses else 0.0,
            "loss_presence": float(np.mean(presence_losses)) if presence_losses else 0.0,
            "loss_equip_coverage": float(np.mean(cov_losses)) if cov_losses else 0.0,
            "loss_noise_suppression": float(np.mean(noise_losses)) if noise_losses else 0.0,
            "mean_w_site": float(np.mean(epoch_w_site)) if epoch_w_site else 0.0,
            "mean_w_equip": float(np.mean(epoch_w_equip)) if epoch_w_equip else 0.0,
            "num_samples_seen": int(num_samples_seen),
            "weight_coords": float(weight_coords),
            "weight_equip_coverage": float(weight_equip_coverage),
            "weight_noise_suppression": float(weight_noise_suppression),
            "train_iou_site": float(np.mean(train_iou[:, 0])) if train_iou.size else 0.0,
            "train_iou_equip": float(np.mean(train_iou[:, 1])) if train_iou.size else 0.0,
            "train_mean_box_area": float(np.mean(train_area)) if train_area.size else 0.0,
            "train_equipment_coverage": equipment_coverage(train_images, train_pred),
        }

        if val_idx:
            val_images, val_targets, _ = _batch_from_items(items, val_idx)
            val_pred, _ = model(torch.from_numpy(val_images).float())
            val_pred = val_pred.detach().cpu().numpy()
            val_pred = _cxcywh_to_xyxy_np(val_pred)
            val_pred = sort_boxes(val_pred)
            val_targets = sort_boxes(val_targets)
            val_iou = iou(val_pred, val_targets)
            entry.update(
                {
                    "val_iou_site": float(np.mean(val_iou[:, 0])) if val_iou.size else 0.0,
                    "val_iou_equip": float(np.mean(val_iou[:, 1])) if val_iou.size else 0.0,
                    "val_equipment_coverage": equipment_coverage(val_images, val_pred),
                }
            )

        logs.append(entry)

    out_model.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "input_channels": input_channels, "page_types": ["SITE_PLAN", "EQUIPMENT_LAYOUT"]}, out_model)

    return {
        "samples_total": len(items),
        "samples_train": len(train_idx),
        "samples_val": len(val_idx),
        "epochs": max(1, epochs),
        "config": {
            "weight_presence": float(weight_presence),
            "loss_weight_schedule": {
                "epochs_1_40": {
                    "coords": 0.5,
                    "equip": 0.1,
                    "noise": 0.05,
                },
                "epochs_41_120": {
                    "coords": 0.3,
                    "equip": 0.2,
                    "noise": 0.1,
                },
            },
            "curriculum_high_q": float(curriculum_high_q),
            "curriculum_low_q": float(curriculum_low_q),
        },
        "log": logs,
        "model_path": str(out_model),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train CNN box regressor from teacher pseudo labels.")
    parser.add_argument("--dataset_dir", default="../../dataset")
    parser.add_argument("--out", default="model.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--weight_presence", type=float, default=0.15)
    parser.add_argument("--curriculum_high_q", type=float, default=0.85)
    parser.add_argument("--curriculum_low_q", type=float, default=0.20)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    out_model = Path(args.out).resolve()

    result = train(
        dataset_dir=dataset_dir,
        out_model=out_model,
        epochs=args.epochs,
        batch=args.batch,
        lr=args.lr,
        seed=args.seed,
        weight_presence=args.weight_presence,
        curriculum_high_q=args.curriculum_high_q,
        curriculum_low_q=args.curriculum_low_q,
    )

    train_log_path = out_model.with_name("train_log.json")
    train_log_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Saved model: {out_model}")
    print(f"Saved train log: {train_log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
