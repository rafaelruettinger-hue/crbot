"""Handkarten erkennen: Ausschnitt jeder Kartenposition mit gespeicherten Vorlagen vergleichen.

Vorlagen liegen in config/cards/<name>__<n>.png, Infos (Kosten, Rolle) in config/cards.json.
Rollen: tank, troop, spell, building
"""
import json
import unicodedata
from dataclasses import dataclass

import cv2
import numpy as np

from crbot.paths import CONFIG_DIR

CARDS_DIR = CONFIG_DIR / "cards"
CARDS_INFO = CONFIG_DIR / "cards.json"

# Ausschnitt um die Kartenmitte (Bildbereich der Karte, ohne Kostenanzeige unten)
HALF_W, TOP, BOTTOM = 60, 80, 40
MATCH_SIZE = (64, 80)
MIN_SCORE = 0.60
UNKNOWN_COST = 4


@dataclass
class Card:
    slot: int          # 1–4
    name: str          # "?" wenn unbekannt
    score: float
    cost: int
    role: str          # tank / troop / spell / building


def crop_slot(img: np.ndarray, center) -> np.ndarray:
    x, y = center
    h, w = img.shape[:2]
    return img[max(y - TOP, 0):min(y + BOTTOM, h), max(x - HALF_W, 0):min(x + HALF_W, w)].copy()


def to_feature(crop: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    return cv2.resize(gray, MATCH_SIZE).astype(np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Korrelation zweier gleich großer Merkmalsbilder (-1 … 1), robust gegen Helligkeit."""
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0])


def load_info() -> dict:
    if not CARDS_INFO.exists():
        return {}
    return {unicodedata.normalize("NFC", k): v for k, v in json.loads(CARDS_INFO.read_text()).items()}


def save_info(info: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    CARDS_INFO.write_text(json.dumps(info, indent=2, ensure_ascii=False, sort_keys=True))


def load_templates() -> list[tuple[str, np.ndarray]]:
    out = []
    if CARDS_DIR.exists():
        for p in sorted(CARDS_DIR.glob("*.png")):
            img = cv2.imread(str(p))
            if img is not None:
                out.append((unicodedata.normalize("NFC", p.stem.split("__")[0]), to_feature(img)))
    return out


def best_match(feature: np.ndarray, templates) -> tuple[str, float]:
    best, score = "?", -1.0
    for name, tpl in templates:
        s = similarity(feature, tpl)
        if s > score:
            best, score = name, s
    return best, score


class HandReader:
    def __init__(self, points: dict):
        self.slots = [points[f"card{i}"] for i in range(1, 5)]
        self.templates = load_templates()
        self.info = load_info()

    def read(self, img: np.ndarray) -> list[Card]:
        hand = []
        for i, center in enumerate(self.slots, start=1):
            name, score = best_match(to_feature(crop_slot(img, center)), self.templates)
            if score < MIN_SCORE:
                name = "?"
            meta = self.info.get(name, {})
            hand.append(Card(i, name, score, meta.get("cost", UNKNOWN_COST), meta.get("role", "troop")))
        return hand
