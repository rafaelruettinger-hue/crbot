"""Zwischen den Kämpfen selbst durch die Menüs klicken.

Der Bot kennt keine Menüs. Du zeigst ihm einmal die Knöpfe (teach), er merkt sich für jeden
Knopf Position + Aussehen. Sieht er später an derselben Stelle denselben Knopf, drückt er ihn.
Zuletzt beigebrachte Knöpfe haben Vorrang (sie liegen „tiefer“ im Menü).
"""
import json
from dataclasses import dataclass

import cv2
import numpy as np

from crbot.paths import CONFIG_DIR

BUTTONS_DIR = CONFIG_DIR / "buttons"
BUTTONS_FILE = CONFIG_DIR / "buttons.json"
HALF = 45          # Vorlage: 90x90 Pixel um den Klickpunkt
SEARCH = 14        # so viel darf der Knopf verschoben sein
MIN_SCORE = 0.80


@dataclass
class Button:
    name: str
    x: int
    y: int
    tpl: np.ndarray


def gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def cut(img: np.ndarray, x: int, y: int, half: int) -> np.ndarray:
    h, w = img.shape[:2]
    return img[max(y - half, 0):min(y + half, h), max(x - half, 0):min(x + half, w)]


def load_list() -> list[dict]:
    return json.loads(BUTTONS_FILE.read_text()) if BUTTONS_FILE.exists() else []


def save_button(img: np.ndarray, x: int, y: int, buttons: list[dict]) -> dict:
    """Knopf (Bildausschnitt + Position) speichern und an die Liste anhängen."""
    BUTTONS_DIR.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(b["name"].removeprefix("knopf")) for b in buttons] or [0])
    entry = {"name": f"knopf{n}", "x": int(x), "y": int(y)}
    cv2.imwrite(str(BUTTONS_DIR / f"{entry['name']}.png"), cut(img, int(x), int(y), HALF))
    buttons.append(entry)
    BUTTONS_FILE.write_text(json.dumps(buttons, indent=2))
    return entry


class Navigator:
    def __init__(self):
        self.buttons: list[Button] = []
        for b in load_list():
            tpl = cv2.imread(str(BUTTONS_DIR / f"{b['name']}.png"), cv2.IMREAD_GRAYSCALE)
            if tpl is not None and tpl.std() > 3:
                self.buttons.append(Button(b["name"], b["x"], b["y"], tpl))

    def find(self, img: np.ndarray) -> Button | None:
        g = gray(img)
        for b in reversed(self.buttons):
            region = cut(g, b.x, b.y, HALF + SEARCH)
            if region.shape[0] < b.tpl.shape[0] or region.shape[1] < b.tpl.shape[1]:
                continue
            if cv2.matchTemplate(region, b.tpl, cv2.TM_CCOEFF_NORMED).max() >= MIN_SCORE:
                return b
        return None
