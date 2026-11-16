"""Während Kämpfen Handkarten-Ausschnitte sammeln -> data/unknown_cards/.
Speichert nur Karten, die neu aussehen. Danach: uv run python -m crbot.main label"""
import time

import cv2

from crbot.device import Device
from crbot.paths import DATA_DIR
from crbot.vision.hand import crop_slot, load_templates, similarity, to_feature

UNKNOWN_DIR = DATA_DIR / "unknown_cards"
SAME = 0.85  # ab dieser Ähnlichkeit gilt ein Ausschnitt als "schon bekannt"


def main(points: dict, seconds: int = 180):
    UNKNOWN_DIR.mkdir(parents=True, exist_ok=True)
    dev = Device.load()
    slots = [points[f"card{i}"] for i in range(1, 5)]
    known = [f for _, f in load_templates()]
    known += [to_feature(cv2.imread(str(p))) for p in UNKNOWN_DIR.glob("*.png")]
    saved, t_end = 0, time.time() + seconds
    print(f"🃏 Sammle {seconds}s lang Handkarten. Spiel dabei normal (selbst), damit viele Karten durchrotieren.")
    try:
        while time.time() < t_end:
            try:
                img = dev.screenshot()
            except RuntimeError as e:
                print(f"  ⚠️  {e}")
                time.sleep(2)
                continue
            for i, c in enumerate(slots, start=1):
                crop = crop_slot(img, c)
                f = to_feature(crop)
                if f.std() < 8:  # leer/einfarbig (z. B. Ladebildschirm)
                    continue
                if any(similarity(f, k) >= SAME for k in known):
                    continue
                path = UNKNOWN_DIR / f"{int(time.time() * 1000)}_s{i}.png"
                cv2.imwrite(str(path), crop)
                known.append(f)
                saved += 1
                print(f"  neu: {path.name}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    print(f"💾 {saved} neue Karten-Ausschnitte. Jetzt benennen: uv run python -m crbot.main label")
