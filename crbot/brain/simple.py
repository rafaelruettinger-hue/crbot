"""Stufe 1: sehr simpler Bot – ab X Elixier zufällige Karte an zufälligen Punkt."""
import random
import time

from crbot.device import Device
from crbot.vision.elixir import read_elixir


def run(device: Device, points: dict, min_elixir: int = 7):
    cards = [points[f"card{i}"] for i in range(1, 5)]
    targets = [points["bridge_left"], points["bridge_right"], points["behind_king"]]
    print(f"🤖 Bot läuft (spielt ab {min_elixir} Elixier). Stoppen mit Strg+C.")
    try:
        while True:
            img = device.screenshot()
            elixir = read_elixir(img, points)
            if elixir >= min_elixir:
                card, target = random.choice(cards), random.choice(targets)
                device.tap(*card)
                time.sleep(0.15)
                device.tap(*target)
                print(f"  Elixier {elixir} -> Karte bei {card} nach {target}")
                time.sleep(1.0)
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n⏹  Gestoppt.")
