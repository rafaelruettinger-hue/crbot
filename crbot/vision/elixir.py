"""Elixierbalken lesen.

Der Balken hat 10 Segmente: gefüllt = pink, leer = dunkelblau. Wir prüfen je Segment einen Punkt.
Gezählt wird bis zum ersten LEEREN Segment – so stört der helle Glanz nicht, der bei vollem
Balken über die Segmente läuft. Außerdem dient der Balken als sicheres Zeichen „Kampf läuft“:
Nur im Kampf sind an allen zehn Stellen Pink oder Dunkelblau zu sehen.
"""
import numpy as np


def _samples(img: np.ndarray, points: dict):
    (x0, y0), (x1, y1) = points["elixir_start"], points["elixir_end"]
    for i in range(10):
        t = (i + 0.5) / 10
        x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
        b, g, r = img[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3].reshape(-1, 3).mean(axis=0)
        yield r, g, b


def _pink(r, g, b) -> bool:
    return r > 150 and b > 150 and g < 0.8 * r


def _empty(r, g, b) -> bool:
    return r < 80 and g < 100 and 90 < b < 200 and b > g + 40


def read_elixir(img: np.ndarray, points: dict) -> int:
    for i, (r, g, b) in enumerate(_samples(img, points)):
        if _empty(r, g, b):
            return i
    return 10


def bar_visible(img: np.ndarray, points: dict) -> bool:
    """True nur im Kampf: mind. 8 von 10 Punkten sind pink oder leer, und kein Pink rechts von Leer."""
    kinds = ["p" if _pink(*s) else "e" if _empty(*s) else "?" for s in _samples(img, points)]
    if kinds.count("?") > 2:
        return False
    seq = [k for k in kinds if k != "?"]
    return "ep" not in "".join(seq)
