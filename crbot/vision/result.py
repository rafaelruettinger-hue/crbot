"""Ergebnis vom Endbildschirm lesen: Kronen oben (Gegner) und unten (wir) zählen.

Jede verdiente Krone ist ein goldenes Objekt; leere Plätze sind nur Kissen. Zusätzlich steht
bei unserem Sieg der türkise Schriftzug „Gewinner!“ direkt über unseren Kronen.
"""
import cv2
import numpy as np

TOP_ZONE = (380, 660)        # y-Bereich der gegnerischen Kronen
BOTTOM_ZONE = (840, 1100)    # y-Bereich unserer Kronen
LABEL_ZONE = (810, 885, 250, 650)   # y0, y1, x0, x1: „Gewinner!“ bei unserem Sieg
GOLD_LO, GOLD_HI = (14, 150, 190), (33, 255, 255)
CYAN_LO, CYAN_HI = (84, 90, 200), (100, 255, 255)


def count_crowns(hsv: np.ndarray, zone) -> int:
    y0, y1 = zone
    gold = cv2.inRange(hsv[y0:y1], GOLD_LO, GOLD_HI)
    gold = cv2.morphologyEx(gold, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(gold)
    bodies = 0
    for i in range(1, n):
        _, _, w, h, area = stats[i]
        if 2000 <= area <= 7500 and 50 <= w <= 110 and 45 <= h <= 100:   # Kronen-Mittelteil
            bodies += 1
    return min(bodies, 3)


def has_our_label(hsv: np.ndarray) -> bool:
    """Türkiser Schriftzug in der Mitte – aber nicht der Fluss (der ist über die ganze Breite türkis)."""
    y0, y1, x0, x1 = LABEL_ZONE
    cyan = cv2.inRange(hsv[y0:y1], CYAN_LO, CYAN_HI)
    centre = int(cyan[:, x0:x1].sum() // 255)
    sides = int(cyan[:, :x0 - 60].sum() // 255) + int(cyan[:, x1 + 60:].sum() // 255)
    return 2000 <= centre <= 14000 and sides < 400


def read_result(img: np.ndarray, sure: bool = False) -> dict | None:
    """-> {"us": 3, "enemy": 1, "result": "win"|"loss", "reward": 0..1} oder None (kein Endbildschirm).
    sure=True: Wir wissen, dass es der Endbildschirm ist (0:0 ohne Schriftzug = Niederlage)."""
    if img is None or img.shape[0] < BOTTOM_ZONE[1]:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    us, enemy = count_crowns(hsv, BOTTOM_ZONE), count_crowns(hsv, TOP_ZONE)
    our_label = has_our_label(hsv)
    if us == 0 and enemy == 0 and not our_label and not sure:
        return None
    if us != enemy:
        result = "win" if us > enemy else "loss"
    else:
        result = "win" if our_label else "loss"      # Gleichstand -> Entscheidung über Turm-Leben
    reward = 0.5 + (us - enemy) / 6 + (0.1 if result == "win" else -0.1)
    return {"us": us, "enemy": enemy, "result": result, "reward": round(min(max(reward, 0.0), 1.0), 3)}
