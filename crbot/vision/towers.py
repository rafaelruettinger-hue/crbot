"""Lebenspunkte der vier Prinzessinnentürme als Anteil (1.0 = voll) aus den Lebensbalken lesen.

Idee aus ClashRoyaleBuildABot (MIT): Der Balken besteht aus einer hellen (gefüllten) und einer
dunklen (leeren) Farbe; der Anteil der hellen Spalten ist der Lebensanteil.
"""
import numpy as np

BAR_WIDTH = 113                     # Breite des Balkens in Pixeln
BAR_LEFT = -45                      # Balken beginnt so weit links von der Spur-Mitte
OWN_DY, ENEMY_DY = 305, -545        # Balkenhöhe relativ zur Brücken-Messlinie
WINDOW = 75                         # so weit darüber/darunter wird gesucht
# (gefüllt, leer) als BGR
OWN_COLOURS = ((252, 208, 111), (112, 79, 63))
ENEMY_COLOURS = ((93, 35, 224), (68, 49, 90))


def _bar(img: np.ndarray, x0: int, y_mid: int, colours) -> float | None:
    h, w = img.shape[:2]
    y0, y1 = max(y_mid - WINDOW, 0), min(y_mid + WINDOW, h)
    x0, x1 = max(x0, 0), min(x0 + BAR_WIDTH, w)
    crop = img[y0:y1, x0:x1].astype(np.int32)
    full = np.abs(crop - np.array(colours[0])).mean(axis=2) < 38
    empty = np.abs(crop - np.array(colours[1])).mean(axis=2) < 30
    rows = (full | empty).sum(axis=1)
    r = int(rows.argmax())
    if rows[r] < 0.6 * (x1 - x0):                 # kein Balken zu sehen (Turm zerstört oder verdeckt)
        return None
    band = slice(max(r - 3, 0), r + 4)
    full_cols = full[band].sum(axis=0) >= 3
    return round(float(full_cols.sum()) / (x1 - x0), 2)


def read_towers(img: np.ndarray, points: dict) -> dict[str, float | None]:
    """-> {"own_left": 0.96, "own_right": None, "enemy_left": 0.47, "enemy_right": 1.0}"""
    out = {}
    for lane in ("left", "right"):
        bx, by = points[f"bridge_{lane}"]
        out[f"own_{lane}"] = _bar(img, bx + BAR_LEFT, by + OWN_DY, OWN_COLOURS)
        out[f"enemy_{lane}"] = _bar(img, bx + BAR_LEFT, by + ENEMY_DY, ENEMY_COLOURS)
    return out
