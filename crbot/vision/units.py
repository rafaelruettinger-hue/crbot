"""Einheiten auf dem Feld erkennen: WELCHE Einheit steht WO, und gehört sie dem Gegner?

Das Erkennungsmodell (YOLO, 97 Einheiten) stammt aus dem MIT-lizenzierten Projekt
ClashRoyaleBuildABot (siehe models/LIZENZ-ClashRoyaleBuildABot.md). Es wurde auf einem 9:16-Bild
trainiert; wir bilden unseren Bildschirm so darauf ab, dass Fluss und Brücken an derselben Stelle
und in derselben Größe liegen wie im Training.

Freund oder Feind: Gegnerische Einheiten tragen immer ein rotes Level-Abzeichen über dem Kopf.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from crbot.vision.enemies import badge_to_unit, find_badges, zone

MODELS = Path(__file__).parent / "models"
MODEL_FILE = MODELS / "units_M_480x352.onnx"
CLASSES_FILE = MODELS / "units.json"

# Geometrie des Trainingsbildes (368 x 652, davon der Streifen 5 % – 80 % der Höhe)
T_W, T_H, T_Y0, T_Y1 = 368, 652, 0.05, 0.80
T_RIVER_Y, T_CX, T_BRIDGE_GAP = 276.3, 183.0, 198.0
MIN_CONF = 0.35          # so sicher muss das Modell sein …
MIN_CONF_BADGE = 0.20    # … außer ein rotes Abzeichen bestätigt, dass dort ein Gegner steht

# Was für eine Art Gegner ist das? (bestimmt die passende Antwort)
KIND = {
    "small": ["skeleton", "goblin", "spear_goblin", "fire_spirit", "ice_spirit", "electro_spirit",
              "heal_spirit", "guard", "wall_breaker", "golemite", "elixir_golem_small", "rascal_girl"],
    "small_air": ["minion", "bat", "lava_pup"],
    "horde": ["barbarian", "elite_barbarian", "royal_recruit", "royal_hog", "zappy"],
    "tank": ["giant", "royal_giant", "golem", "pekka", "giant_skeleton", "mega_knight", "electro_giant",
             "ice_golem", "elixir_golem_large", "elixir_golem_medium", "hog_rider", "hog", "battle_ram",
             "ram_rider", "sparky", "bowler", "cannon_cart", "goblin_cage", "brawler"],
    "air": ["balloon", "lava_hound", "mega_minion", "inferno_dragon", "flying_machine",
            "phoenix_large", "phoenix_small"],
    "air_splash": ["baby_dragon", "electro_dragon", "skeleton_dragon"],
    "ranged": ["archer", "musketeer", "dart_goblin", "archer_queen", "little_prince", "hunter",
               "rascal_boy", "fisherman"],
    "ranged_splash": ["wizard", "ice_wizard", "electro_wizard", "witch", "night_witch", "mother_witch",
                      "executioner", "bomber", "firecracker", "princess", "magic_archer"],
    "melee": ["knight", "minipekka", "prince", "bandit", "lumberjack", "royal_ghost", "miner",
              "mighty_miner", "golden_knight", "skeleton_king", "monk", "battle_healer", "royal_guardian"],
    "melee_splash": ["valkyrie", "dark_prince"],
}
KIND_OF = {name: kind for kind, names in KIND.items() for name in names}

# Schnelle Angreifer: früh reagieren, sie sind in wenigen Sekunden am Turm.
FAST = {"hog_rider", "hog", "royal_hog", "battle_ram", "ram_rider", "balloon", "elite_barbarian", "bandit",
        "prince", "dark_prince", "lumberjack", "wall_breaker", "miner", "mighty_miner"}

# Ungefähre Elixierkosten je einzelner Einheit (für „nicht mehr ausgeben als der Gegner“).
COST = {"skeleton": 0.3, "bat": 0.4, "goblin": 0.6, "spear_goblin": 0.7, "minion": 1.0, "archer": 1.5,
        "barbarian": 1.0, "elite_barbarian": 3.0, "royal_hog": 1.25, "royal_recruit": 1.2, "zappy": 1.3,
        "fire_spirit": 1, "ice_spirit": 1, "electro_spirit": 1, "heal_spirit": 1, "wall_breaker": 1,
        "guard": 1, "lava_pup": 0.5, "knight": 3, "bomber": 2, "ice_golem": 2, "musketeer": 4,
        "minipekka": 4, "valkyrie": 4, "baby_dragon": 4, "hog_rider": 4, "battle_ram": 4, "dart_goblin": 3,
        "mega_minion": 3, "bandit": 3, "miner": 3, "princess": 3, "ice_wizard": 3, "royal_ghost": 3,
        "giant": 5, "prince": 5, "wizard": 5, "witch": 5, "balloon": 5, "ram_rider": 5, "bowler": 5,
        "executioner": 5, "electro_dragon": 5, "inferno_dragon": 4, "electro_wizard": 4, "lumberjack": 4,
        "dark_prince": 4, "hunter": 4, "royal_giant": 6, "giant_skeleton": 6, "sparky": 6,
        "pekka": 7, "mega_knight": 7, "lava_hound": 7, "electro_giant": 7, "golem": 8}


@dataclass
class Unit:
    name: str          # z. B. "giant" – oder "?" für eine gegnerische Einheit ohne erkannten Namen
    conf: float
    box: tuple         # (x0, y0, x1, y1) in Bildschirm-Pixeln
    side: str          # "enemy" / "ally"
    kind: str          # small, small_air, horde, tank, air, air_splash, ranged, ranged_splash, melee, melee_splash, building, unknown
    air: bool          # fliegt
    hits_air: bool     # kann fliegende Einheiten treffen
    cost: float

    @property
    def pos(self) -> tuple:                      # Füße: unten Mitte
        return ((self.box[0] + self.box[2]) // 2, self.box[3])

    @property
    def fast(self) -> bool:
        return self.name in FAST


class UnitDetector:
    def __init__(self, points: dict, own_units: set[str] | None = None):
        import onnxruntime as ort                # erst hier: ohne das Paket läuft der Bot trotzdem (ohne Namen)

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.sess = ort.InferenceSession(str(MODEL_FILE), opts, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.input_name, (self.mh, self.mw) = inp.name, inp.shape[2:]
        self.dtype = np.float16 if "float16" in inp.type else np.float32
        self.classes = json.loads(CLASSES_FILE.read_text())
        self.points = points
        self.own_units = own_units or set()
        bl, br = points["bridge_left"], points["bridge_right"]
        self.k = (br[0] - bl[0]) / T_BRIDGE_GAP              # unsere Pixel pro Trainingspixel
        self.cx = (bl[0] + br[0]) / 2                        # Arena-Mitte
        self.ry = (bl[1] + br[1]) / 2 - 40                   # Fluss-Mitte (Messpunkt liegt knapp darunter)
        strip_h = (T_Y1 - T_Y0) * T_H
        s = min(self.mw / T_W, self.mh / strip_h)
        self.a = s / self.k
        self.bx = (self.mw - T_W * s) / 2 + s * (T_CX - self.cx / self.k)
        self.by = (self.mh - strip_h * s) / 2 + s * (T_RIVER_Y - T_Y0 * T_H - self.ry / self.k)
        self.matrix = np.array([[self.a, 0, self.bx], [0, self.a, self.by]], np.float32)

    def _raw(self, img: np.ndarray) -> list[tuple]:
        small = cv2.warpAffine(img, self.matrix, (self.mw, self.mh), flags=cv2.INTER_AREA,
                               borderValue=(114, 114, 114))
        x = (cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255).transpose(2, 0, 1)[None]
        pred = self.sess.run(None, {self.input_name: x.astype(self.dtype)})[0][0].astype(np.float32)
        out = []
        for left, top, right, bottom, conf, cls in pred[pred[:, 4] > MIN_CONF_BADGE]:
            box = tuple(int(v) for v in ((left - self.bx) / self.a, (top - self.by) / self.a,
                                         (right - self.bx) / self.a, (bottom - self.by) / self.a))
            out.append((self.classes[int(cls)], float(conf), box))
        return out

    def detect(self, img: np.ndarray) -> list[Unit]:
        """Alle Einheiten im Kampfbereich. Gegner ohne erkannten Namen kommen als "?" dazu.
        Gegner ist, wer ein rotes Level-Abzeichen über dem Kopf trägt."""
        y_top, y_bottom = zone(self.points)
        dets = _drop_duplicates(self._raw(img))              # nach Sicherheit sortiert
        badges = find_badges(img, self.points)

        owner: dict[int, int] = {}                           # Abzeichen -> Index der Erkennung
        for bi, (bx, by, bw, bh) in enumerate(badges):
            cx, cy = bx + (bw / 2 if bw < 45 else 14), by + bh / 2
            best, best_d = None, 1e9
            for di, (_, _, (x0, y0, x1, y1)) in enumerate(dets):
                if di in owner.values():
                    continue
                if x0 - 25 <= cx <= x1 + 25 and y0 - 70 <= cy <= y0 + 45:
                    d = abs((x0 + x1) / 2 - cx) + abs(y0 - cy)
                    if d < best_d:
                        best, best_d = di, d
            if best is not None:
                owner[bi] = best
        with_badge = set(owner.values())

        units = []
        for di, ((name, category, target, transport), conf, box) in enumerate(dets):
            # Gegner: rotes Abzeichen – oder eine Einheit, die wir gar nicht im Deck haben (sehr sicher erkannt)
            enemy = di in with_badge or (bool(self.own_units) and name not in self.own_units and conf >= 0.6)
            if conf < MIN_CONF and di not in with_badge:
                continue
            if not y_top <= (box[1] + box[3]) / 2 <= y_bottom:
                continue
            kind = "building" if category == "building" else KIND_OF.get(name, "melee")
            units.append(Unit(name, conf, box, "enemy" if enemy else "ally", kind, transport == "air",
                              target == "all", COST.get(name, 3.0)))
        for bi, badge in enumerate(badges):                  # rotes Abzeichen, aber kein Name erkannt
            if bi not in owner:
                ux, uy = badge_to_unit(badge)
                units.append(Unit("?", 0.0, (ux - 30, uy - 40, ux + 30, uy + 40), "enemy", "unknown",
                                  False, True, 3.0))
        return units


def _drop_duplicates(dets: list[tuple]) -> list[tuple]:
    """Zwei Namen für fast denselben Kasten -> nur den sichereren behalten."""
    keep = []
    for d in sorted(dets, key=lambda d: d[1], reverse=True):
        x0, y0, x1, y1 = d[2]
        dup = False
        for k in keep:
            a0, b0, a1, b1 = k[2]
            iw, ih = min(x1, a1) - max(x0, a0), min(y1, b1) - max(y0, b0)
            if iw > 0 and ih > 0 and iw * ih > 0.6 * min((x1 - x0) * (y1 - y0), (a1 - a0) * (b1 - b0)):
                dup = True
                break
        if not dup:
            keep.append(d)
    return keep


def draw(img: np.ndarray, units: list[Unit]) -> np.ndarray:
    out = img.copy()
    for u in units:
        colour = (0, 0, 255) if u.side == "enemy" else (255, 160, 0)
        cv2.rectangle(out, u.box[:2], u.box[2:], colour, 3)
        label = f"{u.name} {u.conf:.2f}" if u.name != "?" else "?"
        cv2.putText(out, label, (u.box[0], max(u.box[1] - 8, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
        cv2.putText(out, label, (u.box[0], max(u.box[1] - 8, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)
    return out
