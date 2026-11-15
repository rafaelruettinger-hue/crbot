"""Gegner auf dem Weg zu uns erkennen – über ihre ROTEN Lebensbalken/Level-Abzeichen.

Einfache Heuristik (Stufe 2): Wir zählen kräftig rote Pixel zwischen Fluss-Vorfeld und unserem
Königsturm, getrennt nach linker/rechter Spur. Später ersetzt ein YOLO-Modell diese Logik.
"""
from dataclasses import dataclass

import cv2
import numpy as np

MIN_PIXELS = 60  # ab so vielen roten Pixeln gilt eine Spur als bedroht


@dataclass
class Threat:
    lane: str            # "left" / "right"
    pixels: int
    center: tuple        # (x, y) – Schwerpunkt der roten Pixel ≈ Position der Gegner
    front_y: int         # am weitesten zu uns vorgedrungener Gegner (größtes y)


def zone(points: dict) -> tuple[int, int]:
    """y-Bereich: etwas oberhalb der Brücken (Frühwarnung) bis kurz vor die Karten."""
    bridge_y = (points["bridge_left"][1] + points["bridge_right"][1]) // 2
    card_y = min(points[f"card{i}"][1] for i in range(1, 5))
    return bridge_y - 230, card_y - 170


def red_mask(img: np.ndarray, y0: int, y1: int) -> np.ndarray:
    hsv = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2HSV)
    lo = cv2.inRange(hsv, (0, 150, 140), (8, 255, 255))
    hi = cv2.inRange(hsv, (172, 150, 140), (180, 255, 255))
    return cv2.bitwise_or(lo, hi)


def own_tower_boxes(points: dict) -> list[tuple[int, int, int, int]]:
    """Unsere eigenen Türme haben rote Details – diese Bereiche ignorieren wir (x0, y0, x1, y1)."""
    boxes = []
    for lane in ("left", "right"):
        bx = points[f"bridge_{lane}"][0]
        dy = points[f"defend_{lane}"][1]
        boxes.append((bx - 80, dy - 20, bx + 80, dy + 110))
    kx = (points["bridge_left"][0] + points["bridge_right"][0]) // 2
    ky = points["behind_king"][1]
    boxes.append((kx - 120, ky - 230, kx + 120, ky + 20))
    return boxes


def find_threats(img: np.ndarray, points: dict) -> dict[str, Threat]:
    y0, y1 = zone(points)
    mask = red_mask(img, y0, y1)
    for x0, by0, x1, by1 in own_tower_boxes(points):
        mask[max(by0 - y0, 0):max(by1 - y0, 0), max(x0, 0):max(x1, 0)] = 0
    mid = img.shape[1] // 2
    threats = {}
    for lane, xs in (("left", slice(0, mid)), ("right", slice(mid, img.shape[1]))):
        part = mask[:, xs]
        ys, xs_idx = np.nonzero(part)
        if len(ys) < MIN_PIXELS:
            continue
        offset = 0 if lane == "left" else mid
        cx, cy = int(xs_idx.mean()) + offset, int(ys.mean()) + y0
        front = int(np.percentile(ys, 95)) + y0
        threats[lane] = Threat(lane, len(ys), (cx, cy), front)
    return threats


def debug_overlay(img: np.ndarray, points: dict, threats: dict) -> np.ndarray:
    out = img.copy()
    y0, y1 = zone(points)
    cv2.rectangle(out, (0, y0), (img.shape[1] - 1, y1), (255, 255, 0), 2)
    for x0, by0, x1, by1 in own_tower_boxes(points):
        cv2.rectangle(out, (x0, by0), (x1, by1), (255, 0, 0), 2)
    mask = red_mask(img, y0, y1)
    out[y0:y1][mask > 0] = (0, 255, 255)
    for t in threats.values():
        cv2.circle(out, t.center, 25, (0, 0, 255), 4)
        cv2.putText(out, f"{t.lane} {t.pixels}", (t.center[0] - 60, t.center[1] - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
    return out
