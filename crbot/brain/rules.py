"""Stufe 2/3: Regel-Bot.

Merkhilfe – „V-K-P“:
  V = Verteidigen: Gegner auf unserer Seite? -> passende Karte auf die bedrohte Spur.
  K = Konter:      Nach erfolgreicher Verteidigung auf DERSELBEN Spur angreifen.
  P = Puffer:      Sonst sparen – erst ab 9 Elixier angreifen, damit nichts verfällt.
"""
import time

from crbot.device import Device
from crbot.vision.elixir import read_elixir
from crbot.vision.enemies import find_threats
from crbot.vision.hand import Card, HandReader

BIG_THREAT = 220        # so viele rote Pixel = große Gruppe -> Zauber lohnt sich
LANE_COOLDOWN = 2.5     # Sekunden Pause pro Spur nach einer Verteidigung
PLAY_PAUSE = 0.9        # Pause nach jedem Zug (Elixieranzeige braucht kurz)
MIN_KNOWN_CARDS = 2     # weniger erkannt = vermutlich kein Kampf (Menü) -> nichts tun


class RuleBot:
    def __init__(self, device: Device, points: dict):
        self.dev, self.p = device, points
        self.hand_reader = HandReader(points)
        self.last_defend = {"left": 0.0, "right": 0.0}
        self.counter_lane = "left"

    # ---------- Hilfen ----------
    def pick(self, hand: list[Card], elixir: int, roles: tuple[str, ...], cheapest=True) -> Card | None:
        cands = [c for c in hand if c.role in roles and c.cost <= elixir]
        if not cands:
            return None
        return sorted(cands, key=lambda c: c.cost, reverse=not cheapest)[0]

    def play(self, card: Card, target, why: str):
        self.dev.tap(*self.p[f"card{card.slot}"])
        time.sleep(0.12)
        self.dev.tap(*target)
        print(f"  ▶ {card.name} ({card.cost}) -> {tuple(target)}  [{why}]")
        time.sleep(PLAY_PAUSE)

    def building_spot(self, lane: str):
        dx, dy = self.p[f"defend_{lane}"]
        return (int((dx + 450) / 2), dy + 40)  # Richtung Mitte: zieht Gegner zwischen die Türme

    # ---------- Entscheidung ----------
    def step(self) -> bool:
        img = self.dev.screenshot()
        hand = self.hand_reader.read(img)
        if sum(c.name != "?" for c in hand) < MIN_KNOWN_CARDS:
            return False
        elixir = read_elixir(img, self.p)
        threats = find_threats(img, self.p)
        now = time.time()

        # V – Verteidigen (größte Bedrohung zuerst)
        for t in sorted(threats.values(), key=lambda t: t.pixels, reverse=True):
            if now - self.last_defend[t.lane] < LANE_COOLDOWN:
                continue
            if t.pixels >= BIG_THREAT and (c := self.pick(hand, elixir, ("spell",), cheapest=False)):
                self.play(c, t.center, f"Zauber auf Gruppe {t.lane}")
            elif c := self.pick(hand, elixir, ("building",)):
                self.play(c, self.building_spot(t.lane), f"Gebäude gegen {t.lane}")
            elif c := self.pick(hand, elixir, ("troop",)):
                self.play(c, self.p[f"defend_{t.lane}"], f"verteidigen {t.lane}")
            elif c := self.pick(hand, elixir, ("tank",)):
                self.play(c, self.p[f"defend_{t.lane}"], f"Tank blockt {t.lane}")
            else:
                continue
            self.last_defend[t.lane] = time.time()
            self.counter_lane = t.lane
            return True

        # K + P – Angreifen erst mit vollem Puffer, auf der Konter-Spur
        if elixir >= 9:
            lane = self.counter_lane
            if c := self.pick(hand, elixir, ("tank",)):
                self.play(c, self.p[f"defend_{lane}"], f"Tank startet Angriff {lane}")
            elif c := self.pick(hand, elixir, ("troop",), cheapest=False):
                self.play(c, self.p[f"bridge_{lane}"], f"Angriff {lane}")
            elif elixir >= 10 and (c := self.pick(hand, elixir, ("building",))):
                self.play(c, self.building_spot(lane), "Gebäude statt Elixier verschwenden")
            else:
                return False
            return True
        return False


def run(device: Device, points: dict):
    bot = RuleBot(device, points)
    if not bot.hand_reader.templates:
        raise SystemExit("Noch keine Karten bekannt. Erst: collect, dann label.")
    print("🧠 Regel-Bot läuft (V-K-P). Stoppen mit Strg+C.")
    try:
        while True:
            if not bot.step():
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n⏹  Gestoppt.")
