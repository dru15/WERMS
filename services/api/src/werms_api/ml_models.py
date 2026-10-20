"""Two-layer GRU with learned temporal attention; CPU-friendly and reproducible."""

import torch
from torch import nn


class WildfireGRU(nn.Module):
    def __init__(self, variables=15, hidden=32):
        super().__init__()
        self.gru = nn.GRU(
            variables, hidden, num_layers=2, dropout=0.15, batch_first=True
        )
        self.attention = nn.Linear(hidden, 1)
        self.classifier = nn.Linear(hidden, 1)

    def forward(self, inputs):
        states, _ = self.gru(inputs)
        weights = torch.softmax(self.attention(states), dim=1)
        pooled = (states * weights).sum(dim=1)
        return self.classifier(pooled).squeeze(-1)
