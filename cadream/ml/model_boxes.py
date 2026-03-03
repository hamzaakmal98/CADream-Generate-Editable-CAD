from __future__ import annotations


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "PyTorch is required for cadream/ml/model_boxes.py. Install it in your Python env first."
        ) from error


torch, nn = _require_torch()


class TinyBoxRegressor(nn.Module):
    def __init__(self, in_channels: int = 4, hidden_dim: int = 128) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 96, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(96, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 8),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.features(x)
        raw = self.head(features)
        return torch.sigmoid(raw)
