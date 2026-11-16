"""Regel-Bot.

Merkhilfe „V-K-P“:
  V = Verteidigen: Gegner kommt -> passende Antwort auf die bedrohte Spur.
  K = Konter:      Danach auf DERSELBEN Spur angreifen.
  P = Puffer:      Sonst sparen; ab 9 Elixier angreifen, bei 10 IMMER etwas spielen.

Passende Antwort (so gut es ohne Karten-Erkennung des Gegners geht):
  3+ Einheiten (Schwarm)  -> Flächenzauber (Pfeile, sonst Feuerball)
  1 Einheit               -> Einzelziel-Killer (Mini-P.E.K.K.A), sonst Nahkämpfer davor
  2 Einheiten             -> Fernkämpfer dahinter + Nahkämpfer davor
"""
import random
import time
import unicodedata

from crbot.device import Device
from crbot.vision.elixir import bar_visible, read_elixir
from crbot.vision.enemies import Threat, densest_cluster, find_units, group_threats
from crbot.vision.hand import Card, HandReader, in_battle

LANE_COOLDOWN = 2.0     # Sekunden Pause pro Spur nach einer Verteidigung
SPELL_COOLDOWN = 7.0    # nicht zwei Zauber kurz nacheinander auf dieselbe Spur
STATIC_AFTER = 4.0      # steht etwas so lange unbewegt auf der Gegnerseite: Gebäude/Fehlalarm -> ignorieren
DEFEND_WINDOW = 8.0     # in diesem Zeitraum höchstens so viele Verteidiger wie nötig
PLAY_PAUSE = 0.8        # Pause nach jedem Zug (Elixieranzeige braucht kurz)
PUSH_SECONDS = 12       # so lange gilt ein gestarteter Angriff als „läuft“
STATUS_EVERY = 2.0
JITTER = 22

# Spielstil: Stellschrauben, die pro Kampf variiert werden können. Aus den Ergebnissen
# lässt sich später ablesen (und lernen), welche Einstellung häufiger gewinnt.
DEFAULT_STYLE = {"attack_at": 9, "tank_spot": "mix", "support_min": 5, "defend_early": False}
STYLE_CHOICES = {"attack_at": [8, 9, 10], "tank_spot": ["back", "tower", "bridge", "mix"],
                 "support_min": [4, 5, 6], "defend_early": [False, True]}


def random_style() -> dict:
    return {k: random.choice(v) for k, v in STYLE_CHOICES.items()}

# Wissen über Karten (Name wie beim Benennen; unbekannte Namen nutzen nur ihre Rolle).
TAGS = {
    "pfeile": {"swarm_spell"}, "zap": {"swarm_spell"}, "knall": {"swarm_spell"},
    "feuerball": {"area_spell"}, "gift": {"area_spell"},
    "minipekka": {"killer", "melee"}, "pekka": {"killer", "melee"}, "prinz": {"killer", "melee"},
    "ritter": {"melee"}, "walkuere": {"melee", "splash"}, "walküre": {"melee", "splash"},
    "musketier": {"ranged"}, "musketierin": {"ranged"}, "bogenschützen": {"ranged"},
    "bogenschuetzen": {"ranged"}, "speerkobolde": {"ranged"}, "magier": {"ranged", "splash"},
    "babydrache": {"ranged", "splash"}, "lakaien": {"ranged"}, "bomber": {"ranged", "splash"},
    "kobolde": {"melee"}, "skelette": {"melee"},
}


def norm(name: str) -> str:
    return unicodedata.normalize("NFC", name).lower()


def tags(card: Card) -> set:
    return TAGS.get(norm(card.name), set())


class RuleBot:
    def __init__(self, device: Device, points: dict, style: dict | None = None, hand_reader=None):
        self.dev, self.p = device, points
        self.style = {**DEFAULT_STYLE, **(style or {})}
        self.rec = None                                    # optional: Recorder
        self.in_battle = False
        self.hand_reader = hand_reader or HandReader(points)
        self.last_defend = {"left": 0.0, "right": 0.0}
        self.last_spell = {"left": 0.0, "right": 0.0}
        self.recent_defenders = {"left": [], "right": []}
        self.seen_cells: dict = {}                         # Rasterzelle -> (zuerst gesehen, zuletzt gesehen)
        self.push_lane, self.push_until = random.choice(["left", "right"]), 0.0
        self.last_status = 0.0
        self.bridge_y = (points["bridge_left"][1] + points["bridge_right"][1]) // 2
        self.back_y = points["behind_king"][1]
        self.mid_x = (points["bridge_left"][0] + points["bridge_right"][0]) // 2

    # ---------- Orte ----------
    def lane_x(self, lane): return self.p[f"bridge_{lane}"][0]
    def inward(self, lane, px): return self.lane_x(lane) + (px if lane == "left" else -px)

    def clamp(self, x, y):
        """Nur auf unserer Seite ablegen (unterhalb des Flusses, oberhalb der Karten)."""
        return (int(min(max(x, 60), 840)), int(min(max(y, self.bridge_y + 15), self.back_y + 10)))

    def jitter(self, pos, own_side=True):
        x, y = pos[0] + random.randint(-JITTER, JITTER), pos[1] + random.randint(-JITTER, JITTER)
        return self.clamp(x, y) if own_side else (int(x), int(y))

    def spot_in_front(self, t: Threat):      # Nahkämpfer: dem Gegner in den Weg
        return (self.inward(t.lane, 30), max(t.front_y + 150, self.bridge_y + 60))

    def spot_behind(self, lane):             # Fernkämpfer: geschützt neben dem eigenen Turm
        return (self.inward(lane, random.choice([70, 110, 150])), self.p[f"defend_{lane}"][1] + random.choice([60, 120]))

    def spot_pull(self, lane):               # Mitte: zieht Gegner zwischen beide Türme
        return (self.inward(lane, 200), self.p[f"defend_{lane}"][1] + 40)

    def spot_back(self, lane):               # ganz hinten: langsamer Aufbau
        return (self.inward(lane, random.choice([0, 60])), self.back_y - random.choice([0, 60]))

    def spot_bridge(self, lane):
        return self.p[f"bridge_{lane}"]

    def enemy_tower(self, lane):
        return (self.lane_x(lane), self.bridge_y - 430)

    # ---------- Hilfen ----------
    def affordable(self, hand, elixir, pred):
        return sorted((c for c in hand if c.name != "?" and c.cost <= elixir and pred(c)), key=lambda c: c.cost)

    def play(self, card: Card, target, why: str, own_side=True):
        x, y = self.jitter(target, own_side)
        self.dev.tap(*self.p[f"card{card.slot}"])
        time.sleep(0.12)
        self.dev.tap(x, y)
        if self.rec:
            self.rec.action(card, x, y, why)
        print(f"  ▶ {card.name} ({card.cost}) -> ({x}, {y})  [{why}]")
        time.sleep(PLAY_PAUSE)
        return True

    def status(self, elixir, hand, threats):
        if time.time() - self.last_status < STATUS_EVERY:
            return
        self.last_status = time.time()
        h = " ".join(f"{c.name}" for c in hand)
        g = ", ".join(f"{t.lane} {t.count}" for t in threats.values()) or "-"
        print(f"· Elixier {elixir:>2} | Hand: {h} | Gegner: {g}")

    # ---------- V: Verteidigen ----------
    def drop_static(self, units: list, now: float) -> list:
        """Was auf der GEGNERSEITE länger unbewegt steht (Gebäude, Fehlalarm), ist keine Bedrohung."""
        keep = []
        for x, y in units:
            cell = (x // 40, y // 40)
            first, _ = self.seen_cells.get(cell, (now, now))
            self.seen_cells[cell] = (first, now)
            if y < self.bridge_y - 20 and now - first > STATIC_AFTER:
                continue
            keep.append((x, y))
        self.seen_cells = {c: v for c, v in self.seen_cells.items() if now - v[1] < 1.5}
        return keep

    def try_spell(self, t: Threat, hand, elixir, now) -> bool:
        """Flächenzauber nur auf eine ENGE Gruppe nahe der Brücke oder auf unserer Seite."""
        if now - self.last_spell[t.lane] < SPELL_COOLDOWN:
            return False
        n, centre = densest_cluster(t.units)
        if n < 3 or centre[1] < self.bridge_y - 120:
            return False
        target = (centre[0], centre[1] + 60)                # Gegner laufen auf uns zu -> vorhalten
        if c := self.affordable(hand, elixir, lambda c: "swarm_spell" in tags(c)):
            self.last_spell[t.lane] = now
            return self.play(c[0], target, f"enge Gruppe ({n}) {t.lane}: Flächenzauber", own_side=False)
        if n >= 4 and (c := self.affordable(hand, elixir, lambda c: "area_spell" in tags(c))):
            self.last_spell[t.lane] = now
            return self.play(c[0], target, f"enge Gruppe ({n}) {t.lane}: Feuerball", own_side=False)
        return False

    def defend(self, t: Threat, hand, elixir) -> bool:
        lane, now = t.lane, time.time()
        early = 140 if self.style["defend_early"] else 40
        crossed = t.front_y >= self.bridge_y - early       # an/über der Brücke
        at_tower = t.front_y > self.p[f"defend_{lane}"][1] - 60

        if self.try_spell(t, hand, elixir, now):
            return True
        if not crossed:
            return False                                   # noch drüben: Elixier sparen, kommen lassen

        # Nicht mehr Verteidiger als nötig: 1 Gegner -> 1, bis 3 -> 2, mehr -> 3 (am Turm: einer mehr)
        self.recent_defenders[lane] = [x for x in self.recent_defenders[lane] if now - x < DEFEND_WINDOW]
        allowed = (1 if t.count == 1 else 2 if t.count <= 3 else 3) + (1 if at_tower else 0)
        if len(self.recent_defenders[lane]) >= allowed:
            return False

        def troop(card, spot, why):
            self.recent_defenders[lane].append(now)
            return self.play(card, spot, why)

        if t.count == 1:
            if c := self.affordable(hand, elixir, lambda c: "killer" in tags(c)):
                return troop(c[0], self.spot_in_front(t), f"Einzelner Gegner {lane}: Killer davor")
        if t.count >= 2:
            if c := self.affordable(hand, elixir, lambda c: "ranged" in tags(c)):
                return troop(c[0], self.spot_behind(lane), f"{t.count} Gegner {lane}: Fernkämpfer dahinter")
        if c := self.affordable(hand, elixir, lambda c: c.role == "building"):
            return troop(c[0], self.spot_pull(lane), f"Gebäude lenkt {lane} ab")
        if c := self.affordable(hand, elixir, lambda c: "melee" in tags(c)):
            return troop(c[0], self.spot_in_front(t), f"Nahkämpfer stellt sich {lane} in den Weg")
        if c := self.affordable(hand, elixir, lambda c: c.role == "troop"):
            spot = self.spot_behind(lane) if "ranged" in tags(c[0]) else self.spot_in_front(t)
            return troop(c[0], spot, f"verteidigen {lane}")
        if at_tower:                                       # Gegner schon am Turm: Notlösung
            if c := self.affordable(hand, elixir, lambda c: c.role == "tank"):
                return troop(c[0], self.spot_in_front(t), f"Tank blockt {lane}")
        return False

    # ---------- K + P: Angreifen ----------
    def attack(self, hand, elixir) -> bool:
        now, lane = time.time(), self.push_lane
        pushing = now < self.push_until

        if pushing:                                        # Angriff läuft: Unterstützung hinterher
            if elixir >= self.style["support_min"] and (c := self.affordable(hand, elixir, lambda c: "ranged" in tags(c))):
                return self.play(c[-1], (self.lane_x(lane), self.p[f"defend_{lane}"][1] + random.choice([40, 110])),
                                 f"Unterstützung hinter dem Angriff {lane}")
            if elixir >= 8 and (c := self.affordable(hand, elixir, lambda c: c.role == "troop")):
                return self.play(c[-1], self.spot_bridge(lane), f"Nachschub {lane}")
        if elixir < self.style["attack_at"]:
            return False

        if c := self.affordable(hand, elixir, lambda c: c.role == "tank"):
            spots = {"back": (self.spot_back(lane), "hinten aufbauen"),
                     "tower": (self.spot_behind(lane), "neben dem Turm"),
                     "bridge": (self.spot_bridge(lane), "direkt an der Brücke")}
            spot, how = spots.get(self.style["tank_spot"]) or random.choice(list(spots.values()))
            self.push_until = now + PUSH_SECONDS
            return self.play(c[0], spot, f"Tank startet Angriff {lane} ({how})")
        if c := self.affordable(hand, elixir, lambda c: c.role == "troop"):
            card = c[-1]
            if "ranged" in tags(card):
                spot, how = self.spot_back(lane), "Fernkämpfer hinten"
            else:
                spot, how = random.choice([(self.spot_bridge(lane), "Brücke"), (self.spot_back(lane), "hinten")])
            self.push_until = now + PUSH_SECONDS / 2
            return self.play(card, spot, f"Angriff {lane} ({how})")
        if c := self.affordable(hand, elixir, lambda c: c.role == "building"):
            return self.play(c[0], self.spot_pull(lane), "Gebäude in die Mitte")
        if elixir >= 10:                                   # nichts verfallen lassen
            if c := self.affordable(hand, elixir, lambda c: "area_spell" in tags(c)):
                return self.play(c[0], self.enemy_tower(lane), f"Zauber auf Turm {lane}", own_side=False)
            unknown = [c for c in hand if c.name == "?"]
            if unknown:
                return self.play(unknown[0], self.spot_bridge(lane), "unbekannte Karte (voll)")
            if c := self.affordable(hand, elixir, lambda c: c.role == "spell"):
                return self.play(c[0], self.enemy_tower(lane), f"Zauber auf Turm {lane} (voll)", own_side=False)
        return False

    # ---------- ein Schritt ----------
    def step(self, img=None, hand=None) -> bool:
        if img is None:
            img = self.dev.screenshot()
        if hand is None:
            hand = self.hand_reader.read(img)
        self.in_battle = bar_visible(img, self.p) and in_battle(hand)
        if not self.in_battle:
            return False                                   # kein Kampf zu sehen (Menü, Ladebildschirm)
        elixir = read_elixir(img, self.p)
        raw_units = find_units(img, self.p)
        threats = group_threats(self.drop_static(raw_units, time.time()), img.shape[1])
        if self.rec:
            self.rec.state(img, elixir, hand, raw_units)
        self.status(elixir, hand, threats)
        return self.decide(hand, elixir, threats)

    def decide(self, hand, elixir, threats) -> bool:
        now = time.time()
        for t in sorted(threats.values(), key=lambda t: (t.front_y, t.count), reverse=True):
            if now - self.last_defend[t.lane] < LANE_COOLDOWN:
                continue
            if self.defend(t, hand, elixir):
                self.last_defend[t.lane] = time.time()
                self.push_lane = t.lane                    # K: Konter auf derselben Spur
                return True

        if now >= self.push_until and not threats and random.random() < 0.02:
            self.push_lane = random.choice(["left", "right"])
        return self.attack(hand, elixir)


def run(device: Device, points: dict):
    bot = RuleBot(device, points)
    if not bot.hand_reader.templates:
        raise SystemExit("Noch keine Karten bekannt. Erst: collect, dann label.")
    print("🧠 Regel-Bot läuft (V-K-P). Stoppen mit Strg+C.")
    try:
        while True:
            try:
                if not bot.step():
                    time.sleep(0.2)
            except RuntimeError as e:
                print(f"  ⚠️  {e} – versuche es weiter …")
                time.sleep(2)
    except KeyboardInterrupt:
        print("\n⏹  Gestoppt.")


def run_auto(device: Device, points: dict, max_games: int | None = None):
    """Dauerbetrieb: Kampf spielen, mitschreiben, danach selbst den nächsten Kampf starten."""
    from crbot.brain.learn import choose_style, load_games, summary
    from crbot.nav import Navigator
    from crbot.recorder import Recorder

    nav, reader = Navigator(), HandReader(points)
    if not reader.templates:
        raise SystemExit("Noch keine Karten bekannt. Erst: collect, dann label.")
    if not nav.buttons:
        raise SystemExit("Der Bot kennt noch keine Menü-Knöpfe. Erst: uv run python -m crbot.main teach")
    print(f"♾️  Dauerbetrieb mit {len(nav.buttons)} Knöpfen. Stoppen mit Strg+C.")
    bot = rec = None
    games, last_battle, last_seen, hinted = 0, 0.0, time.time(), False

    def end_game(img, sure=False):
        nonlocal bot, rec, games
        meta = rec.finish(img, sure)
        if meta["seconds"] < 20 and meta["actions"] == 0:   # Fehlstart (kein echter Kampf) -> verwerfen
            import shutil
            shutil.rmtree(rec.dir, ignore_errors=True)
            bot = rec = None
            return
        games += 1
        res = meta["result"]
        outcome = ("🏆 Sieg" if res["result"] == "win" else "💀 Niederlage") + f" {res['us']}:{res['enemy']}" if res else "Ergebnis unklar"
        print(f"💾 Kampf {games}: {outcome} – {meta['actions']} Züge, {meta['frames']} Bilder -> {rec.dir.name}")
        print(summary(load_games()))
        bot = rec = None

    try:
        while max_games is None or games < max_games:
            try:
                img = device.screenshot()
            except RuntimeError as e:
                print(f"  ⚠️  {e} – versuche es weiter …")
                time.sleep(2)
                continue
            if btn := nav.find(img):                       # Menü/Endbildschirm: Knopf drücken
                if rec:
                    end_game(img, sure=True)
                    if max_games is not None and games >= max_games:
                        break
                print(f"  🔘 {btn.name}")
                device.tap(btn.x, btn.y)
                last_seen, hinted = time.time(), False
                time.sleep(2.0)
                continue
            hand = reader.read(img)
            if bar_visible(img, points) and in_battle(hand):   # Kampf läuft
                if rec is None:
                    known = load_games()
                    style = choose_style(known)
                    bot = RuleBot(device, points, style, reader)
                    bot.rec = rec = Recorder(style)
                    print(f"\n⚔️  Kampf {games + 1} – Stil (gelernt aus {len(known)} Kämpfen): {style}")
                last_battle = last_seen = time.time()
                hinted = False
                if not bot.step(img, hand):
                    time.sleep(0.15)
                continue
            if rec and time.time() - last_battle > 15:      # Kampf vorbei, aber kein bekannter Knopf
                end_game(img)
            if not hinted and time.time() - last_seen > 45:
                hinted = True
                print("  ❓ Unbekannter Bildschirm. Knopf dafür beibringen: Strg+C, dann  uv run python -m crbot.main teach")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    if rec:
        rec.finish(None)
    print(f"\n⏹  Gestoppt nach {games} Kämpfen. Aufzeichnungen: data/games/")
