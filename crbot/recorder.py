"""Jeden Kampf mitschreiben -> data/games/<Zeitstempel>/

  log.jsonl   eine Zeile pro Beobachtung (Elixier, Hand, Gegner) und pro Zug (Karte, Ort, Grund)
  frames/     1 Bild pro Sekunde (halbe Auflösung, JPEG) – daraus lernen spätere Modelle
  end.png     Endbildschirm (für die Auswertung: gewonnen/verloren, Kronen)
  meta.json   Spielstil dieses Kampfes, Dauer, Anzahl Züge

Das ist der Rohstoff fürs Lernen: Situation -> Zug -> Ergebnis.
"""
import json
import time

import cv2

from crbot.paths import DATA_DIR
from crbot.vision.result import read_result

GAMES_DIR = DATA_DIR / "games"
FRAME_EVERY = 1.0


class Recorder:
    def __init__(self, style: dict):
        base, n = time.strftime("%Y%m%d-%H%M%S"), 1
        self.dir = GAMES_DIR / base
        while self.dir.exists():
            n += 1
            self.dir = GAMES_DIR / f"{base}-{n}"
        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        self.log = open(self.dir / "log.jsonl", "a", encoding="utf-8")
        self.style, self.t0 = style, time.time()
        self.last_frame, self.frames, self.actions = 0.0, 0, 0

    def _t(self):
        return round(time.time() - self.t0, 2)

    def _write(self, row: dict):
        self.log.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.log.flush()

    def state(self, img, elixir, hand, units):
        frame = None
        if time.time() - self.last_frame >= FRAME_EVERY:
            self.last_frame = time.time()
            self.frames += 1
            frame = f"{self.frames:05d}.jpg"
            small = cv2.resize(img, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(self.dir / "frames" / frame), small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        enemies = [list(u) for u in units]
        self._write({"t": self._t(), "elixir": elixir, "hand": [c.name for c in hand],
                     "enemies": enemies, "frame": frame})

    def action(self, card, x, y, why):
        self.actions += 1
        self._write({"t": self._t(), "play": {"card": card.name, "slot": card.slot, "cost": card.cost,
                                             "x": x, "y": y, "why": why}})

    def finish(self, end_img=None, sure: bool = False):
        result = None
        if end_img is not None:
            cv2.imwrite(str(self.dir / "end.png"), end_img)
            result = read_result(end_img, sure)
        meta = {"style": self.style, "seconds": round(time.time() - self.t0), "actions": self.actions,
                "frames": self.frames, "result": result}
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=2))
        self.log.close()
        return meta
