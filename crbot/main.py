"""Einstiegspunkt.

  uv run python -m crbot.main connect     # MuMu per ADB finden und verbinden
  uv run python -m crbot.main shot        # Screenshot -> data/shots/
  uv run python -m crbot.main tap X Y     # auf Koordinate tippen
  uv run python -m crbot.main calib       # Punkte einmessen -> config/points.json
  uv run python -m crbot.main elixir      # aktuelles Elixier schätzen
  uv run python -m crbot.main run [MIN]   # Mini-Bot starten (Standard: ab 7 Elixier)
"""
import json
import sys
import time

import cv2

from crbot.device import Device
from crbot.paths import POINTS_FILE, SHOTS_DIR


def load_points() -> dict:
    if not POINTS_FILE.exists():
        raise SystemExit("Keine config/points.json. Zuerst: uv run python -m crbot.main calib")
    return json.loads(POINTS_FILE.read_text())


def main(argv: list[str]):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]

    if cmd == "connect":
        Device.connect()
    elif cmd == "shot":
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        img = Device.load().screenshot()
        ms = (time.time() - t0) * 1000
        cv2.imwrite(str(SHOTS_DIR / "latest.png"), img)
        cv2.imwrite(str(SHOTS_DIR / f"shot_{int(time.time())}.png"), img)
        h, w = img.shape[:2]
        print(f"📸 {w}x{h} gespeichert in data/shots/latest.png  ({ms:.0f} ms)")
    elif cmd == "tap":
        Device.load().tap(int(args[0]), int(args[1]))
        print(f"👆 Tap auf ({args[0]}, {args[1]})")
    elif cmd == "calib":
        from tools.calibrate import main as calib
        calib()
    elif cmd == "elixir":
        from crbot.vision.elixir import read_elixir
        print(f"💧 Elixier ≈ {read_elixir(Device.load().screenshot(), load_points())}/10")
    elif cmd == "run":
        from crbot.brain.simple import run
        run(Device.load(), load_points(), int(args[0]) if args else 7)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
