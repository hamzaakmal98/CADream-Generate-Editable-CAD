from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from dataset import load_items
from metrics import equipment_coverage, iou, sort_boxes
from metrics_site import bbox_to_mask, boundary_coverage, channel_coverage_ratio, channel_inside_ratio
from model import BoxRegressor, nn, torch


def _split_indices_by_case(items) -> tuple[list[int], list[int], list[str], list[str]]:
    case_to_indices: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        case_to_indices[str(item.case_id)].append(index)

    all_cases = sorted(case_to_indices.keys())
    fixed_val_cases = ["Input_Sample_0", "Input_Sample_1"]
    val_case_ids = [case_id for case_id in fixed_val_cases if case_id in case_to_indices]
    if not val_case_ids and all_cases:
        val_case_ids = all_cases[: max(1, min(2, len(all_cases) - 1))]

    train_case_ids = [case_id for case_id in all_cases if case_id not in set(val_case_ids)]
    if not train_case_ids and val_case_ids:
        train_case_ids = [val_case_ids[-1]]
        val_case_ids = val_case_ids[:-1]

    train_idx: list[int] = []
    for case_id in train_case_ids:
        train_idx.extend(case_to_indices.get(case_id, []))

    val_idx: list[int] = []
    for case_id in val_case_ids:
        val_idx.extend(case_to_indices.get(case_id, []))

    return sorted(train_idx), sorted(val_idx), train_case_ids, val_case_ids


def _batch_from_items(items, indices):
    images = np.stack([items[i].image for i in indices], axis=0)
    targets = np.stack([items[i].target for i in indices], axis=0)
    presence = np.stack([items[i].presence for i in indices], axis=0)
    return images, targets, presence


def _xyxy_to_cxcywh_torch(boxes):
    x1 = torch.minimum(boxes[..., 0], boxes[..., 2])
    y1 = torch.minimum(boxes[..., 1], boxes[..., 3])
    x2 = torch.maximum(boxes[..., 0], boxes[..., 2])
    y2 = torch.maximum(boxes[..., 1], boxes[..., 3])
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    w = torch.clamp(x2 - x1, min=1e-6)
    h = torch.clamp(y2 - y1, min=1e-6)
    return torch.stack([cx, cy, w, h], dim=-1)


def _cxcywh_to_xyxy_torch(boxes):
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


def _coords_penalty(pred_cxcywh):
    widths = pred_cxcywh[..., 2]
    heights = pred_cxcywh[..., 3]
    min_size = 0.02
    return torch.relu(min_size - widths).mean() + torch.relu(min_size - heights).mean()


def _img_bbox_to_model_bbox(bb_img: np.ndarray, global_bbox: np.ndarray | None) -> np.ndarray | None:
    if global_bbox is None or global_bbox.size != 4:
        return None
    x1, y1, x2, y2 = [float(v) for v in bb_img]
    gx1, gy1, gx2, gy2 = [float(v) for v in global_bbox]
    span_x = max(1e-9, gx2 - gx1)
    span_y = max(1e-9, gy2 - gy1)
    wx1 = gx1 + x1 * span_x
    wx2 = gx1 + x2 * span_x
    wy1 = gy1 + (1.0 - y1) * span_y
    wy2 = gy1 + (1.0 - y2) * span_y
    return np.asarray([min(wx1, wx2), min(wy1, wy2), max(wx1, wx2), max(wy1, wy2)], dtype=np.float32)


def _composite_score(entry: dict) -> float:
    w_equip = 0.45
    w_site = 0.15  # reduced from 0.25
    w_boundary = 0.35  # increased from 0.20
    w_noise = 0.10
    val_equip = float(entry.get("val_iou_equip", 0.0))
    val_site = float(entry.get("val_iou_site", 0.0))
    boundary = entry.get("val_boundary_coverage_site")
    noise = float(entry.get("val_noise_ratio_site", 0.0))

    # Block promotion if boundary coverage is too low
    if boundary is not None and float(boundary) < 0.60:
        return -1.0  # Hard block: not promotable

    if boundary is None:
        renorm = w_equip + w_site + w_noise
        return (w_equip * val_equip + w_site * val_site - w_noise * noise) / max(1e-9, renorm)
    return w_equip * val_equip + w_site * val_site + w_boundary * float(boundary) - w_noise * noise


def _save_val_visuals(output_dir: Path, epoch: int, val_idx: list[int], items, val_images: np.ndarray, val_pred_raw: np.ndarray) -> None:
    from PIL import Image, ImageDraw

    epoch_dir = output_dir / "val_preds" / f"epoch_{epoch:03d}"
    epoch_dir.mkdir(parents=True, exist_ok=True)

    for local_index, item_index in enumerate(val_idx):
        item = items[item_index]
        case_name = str(item.case_id)
        crop_name = str(item.crop_id) if item.crop_id is not None else "full"
        image = np.clip(val_images[local_index, 0] * 255.0, 0, 255).astype(np.uint8)
        canvas = Image.fromarray(image, mode="L").convert("RGB")
        draw = ImageDraw.Draw(canvas)
        h, w = image.shape
        x1, y1, x2, y2 = [float(v) for v in val_pred_raw[local_index, 0, :]]
        px1 = int(max(0, min(w - 1, round(x1 * w))))
        px2 = int(max(0, min(w - 1, round(x2 * w))))
        py1 = int(max(0, min(h - 1, round(y1 * h))))
        py2 = int(max(0, min(h - 1, round(y2 * h))))
        draw.rectangle([min(px1, px2), min(py1, py2), max(px1, px2), max(py1, py2)], outline=(255, 64, 64), width=2)
        out_path = epoch_dir / f"{case_name}_{crop_name}_site.png"
        canvas.save(out_path)


def _soft_box_mask(h, w, box, slope = 30.0):
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


def _equipment_aux_losses(images, pred):
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



def _loss_weight_schedule(epoch_index: int) -> tuple[float, float, float, float]:
    epoch_num = int(epoch_index) + 1
    if epoch_num <= 40:
        return 0.5, 0.1, 0.05, 0.20
    return 0.3, 0.2, 0.1, 0.30


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
    save_val_visuals: bool = False,
    save_val_visuals_every: int = 5,
) -> dict:
    items = load_items(dataset_dir)
    if not items:
        raise RuntimeError("No samples passed confidence thresholds")

    train_idx, val_idx, train_case_ids, val_case_ids = _split_indices_by_case(items)
    input_channels = int(items[0].image.shape[0])
    model = BoxRegressor(in_channels=input_channels)
    optim = torch.optim.Adam(model.parameters(), lr=lr)
    smooth_l1 = nn.SmoothL1Loss(reduction="none")
    bce_logits = nn.BCEWithLogitsLoss(reduction="none")

    logs: list[dict] = []

    for epoch in range(max(1, epochs)):
        weight_coords, weight_equip_coverage, weight_noise_suppression, weight_boundary = _loss_weight_schedule(epoch)
        rng = np.random.default_rng(seed + epoch)
        epoch_indices = list(train_idx)
        rng.shuffle(epoch_indices)
        num_samples_seen = len(epoch_indices)
        losses: list[float] = []
        reg_losses: list[float] = []
        cov_losses: list[float] = []
        noise_losses: list[float] = []
        presence_losses: list[float] = []
        boundary_losses: list[float] = []
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

            # --- Boundary coverage loss for SITE_PLAN ---
            # images: [B, 5, H, W], pred_xyxy: [B, 2, 4], targets: [B, 2, 4]
            boundary_channel_idx = 4 if images.shape[1] > 4 else None
            boundary_losses_batch = []
            if boundary_channel_idx is not None:
                site_pred_boxes = pred_xyxy[:, 0, :]  # [B, 4]
                boundary_channels = images[:, boundary_channel_idx, :, :]  # [B, H, W]
                for i in range(images.shape[0]):
                    boundary_mask = boundary_channels[i]
                    boundary_total = boundary_mask.sum().item()
                    if boundary_total > 20.0:
                        # Create mask for predicted site box
                        mask = _soft_box_mask(boundary_mask.shape[0], boundary_mask.shape[1], site_pred_boxes[i].unsqueeze(0)).squeeze(0)
                        boundary_in = (boundary_mask * mask).sum().item()
                        boundary_coverage = boundary_in / (boundary_total + 1e-6)
                        boundary_loss = 1.0 - boundary_coverage
                        boundary_losses_batch.append(boundary_loss)
                    else:
                        boundary_losses_batch.append(0.0)
                boundary_losses_tensor = torch.tensor(boundary_losses_batch, dtype=images.dtype, device=images.device)
                weighted_boundary = boundary_losses_tensor.mean()
            else:
                weighted_boundary = torch.tensor(0.0, dtype=images.dtype, device=images.device)
            boundary_losses.append(float(weighted_boundary.item()))

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
                + weight_boundary * weighted_boundary
            )

            optim.zero_grad()
            loss.backward()
            optim.step()
            losses.append(float(loss.item()))
            reg_losses.append(float(weighted_reg.item()))
            presence_losses.append(float(weighted_presence.item()))
            cov_losses.append(float(weighted_cov.item()))
            noise_losses.append(float(weighted_noise.item()))
            # boundary_losses already appended above

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
            "loss_boundary_coverage": float(np.mean(boundary_losses)) if boundary_losses else 0.0,
            "mean_w_site": float(np.mean(epoch_w_site)) if epoch_w_site else 0.0,
            "mean_w_equip": float(np.mean(epoch_w_equip)) if epoch_w_equip else 0.0,
            "num_samples_seen": int(num_samples_seen),
            "weight_coords": float(weight_coords),
            "weight_equip_coverage": float(weight_equip_coverage),
            "weight_noise_suppression": float(weight_noise_suppression),
            "weight_boundary": float(weight_boundary),
            "train_iou_site": float(np.mean(train_iou[:, 0])) if train_iou.size else 0.0,
            "train_iou_equip": float(np.mean(train_iou[:, 1])) if train_iou.size else 0.0,
            "train_mean_box_area": float(np.mean(train_area)) if train_area.size else 0.0,
            "train_equipment_coverage": equipment_coverage(train_images, train_pred),
        }

        if val_idx:
            val_images, val_targets, _ = _batch_from_items(items, val_idx)
            val_pred, _ = model(torch.from_numpy(val_images).float())
            val_pred_raw = _cxcywh_to_xyxy_np(val_pred.detach().cpu().numpy())
            val_pred = sort_boxes(val_pred_raw)
            val_targets = sort_boxes(val_targets)
            val_iou = iou(val_pred, val_targets)

            site_channel_idx = 2 if val_images.shape[1] > 2 else 0
            noise_channel_idx = 3 if val_images.shape[1] > 3 else 0
            site_context_ratios: list[float] = []
            noise_ratios: list[float] = []
            boundary_coverages: list[float] = []
            per_case: dict[str, dict[str, list[float]]] = {}

            for local_index, item_index in enumerate(val_idx):
                item = items[item_index]
                case_key = str(item.case_id)
                if case_key not in per_case:
                    per_case[case_key] = {
                        "val_iou_site": [],
                        "val_boundary_coverage_site": [],
                        "val_site_context_ratio_site": [],
                        "val_noise_ratio_site": [],
                    }

                pred_site_img = val_pred_raw[local_index, 0, :]
                mask = bbox_to_mask(pred_site_img, val_images.shape[2], val_images.shape[3])
                site_channel = val_images[local_index, site_channel_idx]
                noise_channel = val_images[local_index, noise_channel_idx]
                site_ctx = channel_coverage_ratio(site_channel, mask)
                noise_ratio = channel_inside_ratio(noise_channel, mask)
                site_context_ratios.append(site_ctx)
                noise_ratios.append(noise_ratio)
                per_case[case_key]["val_iou_site"].append(float(val_iou[local_index, 0]))
                per_case[case_key]["val_site_context_ratio_site"].append(site_ctx)
                per_case[case_key]["val_noise_ratio_site"].append(noise_ratio)

                boundary_bbox = item.boundary_bbox_model
                if boundary_bbox is not None and boundary_bbox.size == 4:
                    pred_site_model = _img_bbox_to_model_bbox(pred_site_img, item.global_bbox_model)
                    if pred_site_model is not None:
                        coverage = boundary_coverage(boundary_bbox, pred_site_model)
                        boundary_coverages.append(coverage)
                        per_case[case_key]["val_boundary_coverage_site"].append(coverage)

            entry.update(
                {
                    "val_iou_site": float(np.mean(val_iou[:, 0])) if val_iou.size else 0.0,
                    "val_iou_equip": float(np.mean(val_iou[:, 1])) if val_iou.size else 0.0,
                    "val_equipment_coverage": equipment_coverage(val_images, val_pred),
                    "val_boundary_coverage_site": float(np.mean(boundary_coverages)) if boundary_coverages else None,
                    "val_site_context_ratio_site": float(np.mean(site_context_ratios)) if site_context_ratios else 0.0,
                    "val_noise_ratio_site": float(np.mean(noise_ratios)) if noise_ratios else 0.0,
                }
            )

            if save_val_visuals and ((epoch + 1) % max(1, int(save_val_visuals_every)) == 0):
                _save_val_visuals(out_model.parent, epoch + 1, val_idx, items, val_images, val_pred_raw)

            entry["val_composite_score"] = _composite_score(entry)
            val_by_case: dict[str, dict[str, float | None]] = {}
            for case_key, metrics_map in per_case.items():
                case_entry = {
                    "val_iou_site": float(np.mean(metrics_map["val_iou_site"])) if metrics_map["val_iou_site"] else 0.0,
                    "val_boundary_coverage_site": float(np.mean(metrics_map["val_boundary_coverage_site"])) if metrics_map["val_boundary_coverage_site"] else None,
                    "val_site_context_ratio_site": float(np.mean(metrics_map["val_site_context_ratio_site"])) if metrics_map["val_site_context_ratio_site"] else 0.0,
                    "val_noise_ratio_site": float(np.mean(metrics_map["val_noise_ratio_site"])) if metrics_map["val_noise_ratio_site"] else 0.0,
                }
                case_entry["val_composite_score"] = _composite_score(case_entry)
                val_by_case[case_key] = case_entry
            entry["val_by_case"] = val_by_case

        logs.append(entry)

    out_model.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "input_channels": input_channels, "page_types": ["SITE_PLAN", "EQUIPMENT_LAYOUT"]}, out_model)

    return {
        "samples_total": len(items),
        "samples_train": len(train_idx),
        "samples_val": len(val_idx),
        "train_case_ids": train_case_ids,
        "val_case_ids": val_case_ids,
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
            "composite_score_formula": "0.45*val_iou_equip + 0.15*val_iou_site + 0.35*val_boundary_coverage_site - 0.10*val_noise_ratio_site (promotion blocked if boundary_coverage < 0.60)",
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
    parser.add_argument("--save_val_visuals", action="store_true")
    parser.add_argument("--save_val_visuals_every", type=int, default=5)
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
        save_val_visuals=bool(args.save_val_visuals),
        save_val_visuals_every=max(1, int(args.save_val_visuals_every)),
    )

    train_log_path = out_model.with_name("train_log.json")
    train_log_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Saved model: {out_model}")
    print(f"Saved train log: {train_log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
