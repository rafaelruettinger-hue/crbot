"""Handkarten erkennen: Ausschnitt jeder Kartenposition mit gespeicherten Vorlagen vergleichen.

Vorlagen liegen in config/cards/<name>__<n>.png, Infos (Kosten, Rolle) in config/cards.json.
Rollen: tank, troop, spell, building

Wichtig: Die vier Kartenplätze sind von Hand eingemessen und liegen nie exakt gleich. Deshalb
vergleichen wir nicht deckungsgleich, sondern suchen den KERN jeder Vorlage in einem etwas
größeren Ausschnitt um den Kartenplatz (verschiebungstolerant, ±48 px).
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
CORE_TRIM = 22          # so viel Rand wird von einer Vorlage abgeschnitten -> „Kern“
SEARCH_MARGIN = 26      # so viel größer ist der Suchausschnitt am Kartenplatz
SCALE = 0.5             # halbe Auflösung reicht und ist 4x schneller
MIN_SCORE = 0.60
UNKNOWN_COST = 4


@dataclass
class Card:
    slot: int          # 1–4
    name: str          # "?" wenn unbekannt
    score: float
    cost: int
    role: str          # tank / troop / spell / building


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def crop_slot(img: np.ndarray, center, margin: int = 0) -> np.ndarray:
    x, y = center
    h, w = img.shape[:2]
    return img[max(y - TOP - margin, 0):min(y + BOTTOM + margin, h),
               max(x - HALF_W - margin, 0):min(x + HALF_W + margin, w)].copy()


def small_gray(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return cv2.resize(gray, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)


def core(img: np.ndarray) -> np.ndarray:
    """Kern einer Vorlage (Rand abgeschnitten), verkleinert."""
    t = CORE_TRIM
    inner = img[t:-t, t:-t] if img.shape[0] > 3 * t and img.shape[1] > 3 * t else img
    return small_gray(inner)


def score(search_small: np.ndarray, core_small: np.ndarray) -> float:
    """Beste Übereinstimmung des Kerns irgendwo im Suchbild (-1 … 1)."""
    if search_small.shape[0] < core_small.shape[0] or search_small.shape[1] < core_small.shape[1]:
        return -1.0
    return float(cv2.matchTemplate(search_small, core_small, cv2.TM_CCOEFF_NORMED).max())


def is_blank(img: np.ndarray) -> bool:
    return float(small_gray(img).std()) < 8


def load_info() -> dict:
    if not CARDS_INFO.exists():
        return {}
    return {nfc(k): v for k, v in json.loads(CARDS_INFO.read_text()).items()}


def save_info(info: dict):
    CONFIG_DIR.mkdir(exist_ok=True)
    CARDS_INFO.write_text(json.dumps(info, indent=2, ensure_ascii=False, sort_keys=True))


def load_templates() -> list[tuple[str, np.ndarray]]:
    """Liste aus (Name, Kern)."""
    out = []
    if CARDS_DIR.exists():
        for p in sorted(CARDS_DIR.glob("*.png")):
            img = cv2.imread(str(p))
            if img is not None:
                out.append((nfc(p.stem.split("__")[0]), core(img)))
    return out


def best_match(search_img: np.ndarray, templates) -> tuple[str, float]:
    """search_img: Farbausschnitt (Kartenplatz oder gespeicherter Ausschnitt)."""
    search = small_gray(search_img)
    best, best_score = "?", -1.0
    for name, tpl in templates:
        s = score(search, tpl)
        if s > best_score:
            best, best_score = name, s
    return best, best_score


class HandReader:
    def __init__(self, points: dict):
        self.slots = [points[f"card{i}"] for i in range(1, 5)]
        self.templates = load_templates()
        self.info = load_info()

    def read(self, img: np.ndarray) -> list[Card]:
        """Jede Karte kann nur einmal auf der Hand sein: Die sichersten Treffer werden zuerst
        vergeben, ein zweiter Platz mit demselben Namen bekommt seine nächstbeste Karte oder „?“."""
        cands = []                                   # (Wert, Platz, Name)
        for i, center in enumerate(self.slots, start=1):
            search = small_gray(crop_slot(img, center, SEARCH_MARGIN))
            per_name: dict[str, float] = {}
            for name, tpl in self.templates:
                s = score(search, tpl)
                if s > per_name.get(name, -1.0):
                    per_name[name] = s
            cands += [(s, i, name) for name, s in per_name.items() if s >= MIN_SCORE]
        chosen: dict[int, tuple[str, float]] = {}
        used: set[str] = set()
        for s, i, name in sorted(cands, reverse=True):
            if i not in chosen and name not in used:
                chosen[i] = (name, s)
                used.add(name)
        hand = []
        for i in range(1, 5):
            name, s = chosen.get(i, ("?", 0.0))
            meta = self.info.get(name, {})
            hand.append(Card(i, name, s, meta.get("cost", UNKNOWN_COST), meta.get("role", "troop")))
        return hand


def in_battle(hand: list[Card]) -> bool:
    """Im Kampf sind (fast) immer alle vier Karten erkennbar; ein einzelner Zufallstreffer
    auf einem Menü- oder Endbildschirm zählt nicht."""
    return sum(c.name != "?" for c in hand) >= 2
