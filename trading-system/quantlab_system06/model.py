"""The student: a compact causal TCN that predicts the oracle's hold bit.

A temporal convolutional network rather than an RNN for one reason that matters
on this hardware — every timestep of the K-bar window is processed in parallel,
so an 8 GB card trains it flat out. Three dilated, **causal** convolution blocks
give a receptive field that covers the whole window while guaranteeing the
prediction at the last bar reads no bar after it: dilations 1, 2, 4 over kernel 3
reach back 1 + 2·(1+2+4) = 15 bars per stack, and the window is fed last-bar-last
so the final position's output is the readout.

Small on purpose. The point of v1 is a correct end-to-end path, and a model that
overfits 280k bars of one symbol teaches nothing about the mechanism. Depth and
width are config, so scaling up is a flag, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
from torch import nn


@dataclass
class ModelConfig:
    n_features: int
    window: int = 64                       # bars fed per decision (16h at 15m)
    channels: tuple[int, ...] = (64, 64, 64)
    kernel: int = 3
    dropout: float = 0.1
    dilations: tuple[int, ...] = field(default=())

    def resolved_dilations(self) -> tuple[int, ...]:
        return self.dilations or tuple(2**i for i in range(len(self.channels)))

    def to_dict(self) -> dict:
        return {
            "n_features": self.n_features,
            "window": self.window,
            "channels": list(self.channels),
            "kernel": self.kernel,
            "dropout": self.dropout,
            "dilations": list(self.resolved_dilations()),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ModelConfig":
        return cls(
            n_features=int(payload["n_features"]),
            window=int(payload["window"]),
            channels=tuple(payload["channels"]),
            kernel=int(payload["kernel"]),
            dropout=float(payload["dropout"]),
            dilations=tuple(payload.get("dilations", ())),
        )


class _CausalBlock(nn.Module):
    """Dilated causal conv → GELU → dropout, with a residual connection.

    Causality is enforced by left-padding the input by `(kernel-1)*dilation` and
    trimming the same count off the right after the convolution, so output `t`
    depends only on inputs `<= t`. Getting this wrong leaks the future through the
    receptive field invisibly — the loss simply looks too good.
    """

    def __init__(self, in_ch: int, out_ch: int, kernel: int, dilation: int, dropout: float):
        super().__init__()
        self.pad = (kernel - 1) * dilation
        self.conv = nn.Conv1d(in_ch, out_ch, kernel, dilation=dilation)
        self.act = nn.GELU()
        self.drop = nn.Dropout(dropout)
        self.down = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = nn.functional.pad(x, (self.pad, 0))
        y = self.conv(y)
        y = self.drop(self.act(y))
        residual = x if self.down is None else self.down(x)
        return y + residual


class OracleNet(nn.Module):
    """Windowed features in, one hold-logit out (P(hold) after a sigmoid)."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        dilations = config.resolved_dilations()
        channels = config.channels
        blocks = []
        in_ch = config.n_features
        for out_ch, dilation in zip(channels, dilations):
            blocks.append(_CausalBlock(in_ch, out_ch, config.kernel, dilation, config.dropout))
            in_ch = out_ch
        self.blocks = nn.Sequential(*blocks)
        self.head = nn.Linear(in_ch, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x arrives [batch, window, features]; conv1d wants [batch, features, window].
        y = x.transpose(1, 2)
        y = self.blocks(y)
        last = y[:, :, -1]  # the readout is the last (most recent) bar's channels
        return self.head(last).squeeze(-1)
