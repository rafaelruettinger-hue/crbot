"""Gegnerische Einheiten finden – über ihr ROTES Level-Abzeichen (kleines Quadrat mit Zahl).

Eigene Einheiten haben blaue Abzeichen, Türme gelbe Kronen: Das rote Abzeichen ist also ein
sauberes Merkmal für „gegnerische Einheit“. Wir zählen die Abzeichen pro Spur. Welche Karte es
genau ist, erkennt erst ein trainiertes Modell (nächste Ausbaustufe).
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

BADGE_LO, BADGE_HI = (167, 170, 90), (178, 255, 255)   # kräftiges Karminrot (HSV)
MIN_AREA, MIN_SIDE, MAX_H = 150, 14, 48


@dataclass
class Threat:
    lane: str                      # "left" / "right"
    count: int                     # Anzahl gegnerischer Einheiten
    center: tuple                  # Mittelpunkt der Gruppe (x, y)
    front_y: int                   # am weitesten vorgedrungene Einheit (größtes y)
    units: list = field(default_factory=list)
    spread: int = 0                # Ausdehnung der Gruppe in Pixeln

    @property
    def pixels(self):              # für ältere Aufrufer
        return self.count


def zone(points: dict) -> tuple[int, int]:
    """y-Bereich: etwas oberhalb der Brücken (Frühwarnung) bis kurz vor die Karten."""
    bridge_y = (points["bridge_left"][1] + points["bridge_right"][1]) // 2
    card_y = min(points[f"card{i}"][1] for i in range(1, 5))
    return bridge_y - 260, card_y - 170


def badge_mask(img: np.ndarray, y0: int, y1: int) -> np.ndarray:
    hsv = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BADGE_LO, BADGE_HI)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))


def find_units(img: np.ndarray, points: dict) -> list[tuple[int, int]]:
    """Positionen gegnerischer Einheiten (Abzeichen sitzt über dem Kopf -> etwas nach unten versetzt)."""
    y0, y1 = zone(points)
    n, _, stats, _ = cv2.connectedComponentsWithStats(badge_mask(img, y0, y1))
    units = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < MIN_AREA or w < MIN_SIDE or h < MIN_SIDE or h > MAX_H:
            continue
        # breites Objekt = Abzeichen + Lebensbalken derselben Einheit -> Abzeichen ist links
        cx = x + (w // 2 if w < 45 else 14)
        units.append((int(cx), int(y + y0 + h + 30)))
    return units


def find_threats(img: np.ndarray, points: dict) -> dict[str, Threat]:
    units = find_units(img, points)
    mid = img.shape[1] // 2
    threats = {}
    for lane in ("left", "right"):
        us = [u for u in units if (u[0] < mid) == (lane == "left")]
        if not us:
            continue
        xs, ys = [u[0] for u in us], [u[1] for u in us]
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        threats[lane] = Threat(lane, len(us), (sum(xs) // len(us), sum(ys) // len(us)), max(ys), us, spread)
    return threats


def debug_overlay(img: np.ndarray, points: dict, threats: dict) -> np.ndarray:
    out = img.copy()
    y0, y1 = zone(points)
    cv2.rectangle(out, (0, y0), (img.shape[1] - 1, y1), (255, 255, 0), 2)
    for t in threats.values():
        for u in t.units:
            cv2.circle(out, u, 22, (0, 0, 255), 3)
        cv2.putText(out, f"{t.lane}: {t.count}", (t.center[0] - 60, t.center[1] - 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
    return out
