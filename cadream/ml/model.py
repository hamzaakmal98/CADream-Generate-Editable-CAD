from __future__ import annotations


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except ModuleNotFoundError as error:
        raise RuntimeError("PyTorch is required for cadream/ml/model.py") from error


torch, nn = _require_torch()


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_planes: int, out_planes: int, stride: int = 1) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(out_planes, out_planes, kernel_size=3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_planes)

        if stride != 1 or in_planes != out_planes:
            self.downsample = nn.Sequential(
                nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_planes),
            )
        else:
            self.downsample = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = self.downsample(x)
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = self.relu(out + identity)
        return out


class BoxRegressor(nn.Module):
    def __init__(self, in_channels: int = 4, hidden_dim: int = 128) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, 64, kernel_size=7, stride=2, padding=3, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=3, stride=2, padding=1),
        )

        self.layer1 = self._make_layer(64, 64, blocks=2, stride=1)
        self.layer2 = self._make_layer(64, 128, blocks=2, stride=2)
        self.layer3 = self._make_layer(128, 256, blocks=2, stride=2)
        self.layer4 = self._make_layer(256, 512, blocks=2, stride=2)
        self.pool = nn.AdaptiveAvgPool2d((1, 1))

        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(512, hidden_dim),
            nn.ReLU(inplace=True),
        )

        self.box_head = nn.Linear(hidden_dim, 8)
        self.presence_head = nn.Linear(hidden_dim, 2)

    @staticmethod
    def _make_layer(in_planes: int, out_planes: int, blocks: int, stride: int) -> nn.Sequential:
        layers = [BasicBlock(in_planes, out_planes, stride=stride)]
        for _ in range(1, blocks):
            layers.append(BasicBlock(out_planes, out_planes, stride=1))
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        y = self.stem(x)
        y = self.layer1(y)
        y = self.layer2(y)
        y = self.layer3(y)
        y = self.layer4(y)
        y = self.pool(y)
        y = self.head(y)
        boxes = torch.sigmoid(self.box_head(y)).view(-1, 2, 4)
        presence_logits = self.presence_head(y).view(-1, 2)
        return boxes, presence_logits
