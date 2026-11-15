"""Einstiegspunkt.

Grundlagen
  uv run python -m crbot.main connect       # MuMu per ADB finden und verbinden
  uv run python -m crbot.main shot          # Screenshot -> data/shots/
  uv run python -m crbot.main tap X Y       # auf Koordinate tippen
  uv run python -m crbot.main calib         # Punkte einmessen -> config/points.json

Stufe 2 – Sehen
  uv run python -m crbot.main collect [SEK] # Handkarten sammeln (Standard 180 s)
  uv run python -m crbot.main label         # gesammelte Karten benennen
  uv run python -m crbot.main see           # zeigt, was der Bot gerade erkennt

Bots
  uv run python -m crbot.main run [MIN]     # Zufalls-Bot (Stufe 1)
  uv run python -m crbot.main play          # Regel-Bot (Stufe 2/3)
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


def cmd_shot():
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    dev = Device.load()
    t0 = time.time()
    img = dev.screenshot()
    ms = (time.time() - t0) * 1000
    cv2.imwrite(str(SHOTS_DIR / "latest.png"), img)
    cv2.imwrite(str(SHOTS_DIR / f"shot_{int(time.time())}.png"), img)
    h, w = img.shape[:2]
    print(f"📸 {w}x{h} gespeichert in data/shots/latest.png  ({ms:.0f} ms)")


def cmd_see():
    from crbot.vision.elixir import read_elixir
    from crbot.vision.enemies import debug_overlay, find_threats
    from crbot.vision.hand import HandReader

    pts, dev = load_points(), Device.load()
    t0 = time.time()
    img = dev.screenshot()
    shot_ms = (time.time() - t0) * 1000
    hand = HandReader(pts).read(img)
    threats = find_threats(img, pts)
    print(f"📸 Screenshot: {shot_ms:.0f} ms")
    print(f"💧 Elixier: {read_elixir(img, pts)}/10")
    print("🃏 Hand:   " + " | ".join(f"{c.slot}: {c.name} ({c.score:.2f})" for c in hand))
    if threats:
        for t in threats.values():
            print(f"⚠️  Gegner {t.lane}: {t.pixels} rote Pixel, Mitte {t.center}")
    else:
        print("✅ Keine Gegner auf unserer Seite erkannt")
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(SHOTS_DIR / "debug.png"), debug_overlay(img, pts, threats))
    print("🖼  Bild mit Markierungen: data/shots/debug.png  (öffnen: open data/shots/debug.png)")


def main(argv: list[str]):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]

    if cmd == "connect":
        Device.connect()
    elif cmd == "shot":
        cmd_shot()
    elif cmd == "tap":
        Device.load().tap(int(args[0]), int(args[1]))
        print(f"👆 Tap auf ({args[0]}, {args[1]})")
    elif cmd == "calib":
        from tools.calibrate import main as calib
        calib()
    elif cmd == "elixir":
        from crbot.vision.elixir import read_elixir
        print(f"💧 Elixier ≈ {read_elixir(Device.load().screenshot(), load_points())}/10")
    elif cmd == "collect":
        from tools.collect_cards import main as collect
        collect(load_points(), int(args[0]) if args else 180)
    elif cmd == "label":
        from tools.label_cards import main as label
        label()
    elif cmd == "see":
        cmd_see()
    elif cmd == "run":
        from crbot.brain.simple import run
        run(Device.load(), load_points(), int(args[0]) if args else 7)
    elif cmd == "play":
        from crbot.brain.rules import run
        run(Device.load(), load_points())
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
