"""Elixier aus dem Screenshot lesen (zählt lila gefüllte Segmente des Balkens)."""
import numpy as np


def read_elixir(img: np.ndarray, points: dict) -> int:
    (x0, y0), (x1, y1) = points["elixir_start"], points["elixir_end"]
    filled = 0
    for i in range(10):
        t = (i + 0.5) / 10
        x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
        b, g, r = img[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3].reshape(-1, 3).mean(axis=0)
        # Elixier ist magenta/lila: viel Rot + Blau, wenig Grün
        if r > 150 and b > 150 and g < 120:
            filled += 1
    return filled
