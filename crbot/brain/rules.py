"""Regel-Bot.

Merkhilfe „V-K-P“:
  V = Verteidigen: Gegner kommt -> passende Antwort auf die bedrohte Spur.
  K = Konter:      Danach auf DERSELBEN Spur angreifen.
  P = Puffer:      Sonst sparen; ab 9 Elixier angreifen, bei 10 IMMER etwas spielen.

Die passende Antwort hängt davon ab, WELCHE Einheit der Gegner gespielt hat. Das erkennt
crbot/vision/units.py; die Zuordnung „Gegner -> unsere Karte“ steht in crbot/brain/counters.py.
"""
import random
import time

from crbot.brain.counters import card_tags as tags
from crbot.brain.counters import choose, de
from crbot.brain.tracker import EnemyTracker
from crbot.device import Device
from crbot.vision.elixir import bar_visible, read_elixir
from crbot.vision.enemies import badge_to_unit, find_badges
from crbot.vision.hand import Card, HandReader, in_battle
from crbot.vision.towers import read_towers
from crbot.vision.units import Unit

LANE_COOLDOWN = 1.5     # Sekunden Pause pro Spur nach einer Verteidigung
SPELL_COOLDOWN = 7.0    # nicht zwei Zauber kurz nacheinander auf dieselbe Spur
STATIC_AFTER = 4.0      # steht etwas so lange unbewegt auf der Gegnerseite: Gebäude/Fehlalarm -> ignorieren
DEFEND_WINDOW = 8.0     # Zeitraum, in dem wir nicht mehr Elixier ausgeben als der Gegner
ANSWER_MEMORY = 6.0     # so lange gilt eine Gegnergruppe als „schon beantwortet“
PLAY_PAUSE = 0.8        # Pause nach jedem Zug (Elixieranzeige braucht kurz)
PUSH_SECONDS = 12       # so lange gilt ein gestarteter Angriff als „läuft“
STATUS_EVERY = 2.0
JITTER = 22

# Spielstil: Stellschrauben, die pro Kampf variiert werden können. Aus den Ergebnissen
# lässt sich später ablesen (und lernen), welche Einstellung häufiger gewinnt.
DEFAULT_STYLE = {"attack_at": 9, "tank_spot": "mix", "support_min": 5, "defend_early": False}
STYLE_CHOICES = {"attack_at": [8, 9, 10], "tank_spot": ["back", "tower", "bridge", "mix"],
                 "support_min": [4, 5, 6], "defend_early": [False, True]}

# Unsere Karten -> Name der Einheit im Erkennungsmodell (um eigene von gegnerischen zu trennen)
OWN_UNIT_NAMES = {"ritter": "knight", "bogenschützen": "archer", "bogenschuetzen": "archer", "riese": "giant",
                  "musketier": "musketeer", "musketierin": "musketeer", "minipekka": "minipekka",
                  "lakaien": "minion", "kobolde": "goblin", "speerkobolde": "spear_goblin",
                  "skelette": "skeleton", "walküre": "valkyrie", "bomber": "bomber", "prinz": "prince",
                  "babydrache": "baby_dragon", "magier": "wizard", "hexe": "witch", "pekka": "pekka"}


def random_style() -> dict:
    return {k: random.choice(v) for k, v in STYLE_CHOICES.items()}


def load_detector(points: dict, card_names):
    """Erkennungsmodell laden. Fehlt etwas, spielt der Bot weiter – dann ohne Namen der Gegner."""
    try:
        from crbot.vision.units import UnitDetector
        own = {OWN_UNIT_NAMES[n] for n in card_names if n in OWN_UNIT_NAMES}
        return UnitDetector(points, own)
    except Exception as e:                                   # z. B. onnxruntime nicht installiert
        print(f"  ⚠️  Einheiten-Erkennung nicht verfügbar ({type(e).__name__}: {e}). Spiele ohne Gegner-Namen.")
        return None


class RuleBot:
    def __init__(self, device: Device, points: dict, style: dict | None = None, hand_reader=None,
                 detector="auto"):
        self.dev, self.p = device, points
        self.style = {**DEFAULT_STYLE, **(style or {})}
        self.rec = None                                    # optional: Recorder
        self.in_battle = False
        self.hand_reader = hand_reader or HandReader(points)
        self.detector = (load_detector(points, getattr(self.hand_reader, "info", {}))
                         if detector == "auto" else detector)
        self.last_defend = {"left": 0.0, "right": 0.0}
        self.last_spell = {"left": 0.0, "right": 0.0}
        self.tracker: EnemyTracker | None = None           # zählt Karten und Elixier des Gegners mit
        self.towers: dict = {}                             # zuletzt gelesene Turm-Lebensanteile
        self.tower_gone: dict = {}                         # Turm -> seit wann kein Balken mehr zu sehen ist
        self.tower_hist: dict = {}                         # Turm -> letzte Ablesungen
        self.spent = {"left": [], "right": []}             # (Zeit, Elixier) der letzten Verteidigungszüge
        self.answered = {"left": [], "right": []}          # (Zeit, Gegnername), schon beantwortet
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

    def spot_in_front(self, lane, front_y):  # Nahkämpfer: dem Gegner in den Weg
        return (self.inward(lane, 30), max(front_y + 150, self.bridge_y + 60))

    def spot_on(self, unit: Unit):           # direkt auf den Gegner (ist er noch drüben: an den Brückenausgang)
        x, y = unit.pos
        return (x, max(y - 20, self.bridge_y + 40))

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
        parts = []
        for lane, label in (("left", "links"), ("right", "rechts")):
            names = [u.name for u in threats.get(lane, [])]
            if names:
                parts.append(label + " " + ", ".join(
                    (f"{names.count(n)}× " if names.count(n) > 1 else "") + de(n) for n in dict.fromkeys(names)))
        foe = f" | Gegner-Elixier ≈ {self.tracker.elixir:.0f}" if self.tracker else ""
        print(f"· Elixier {elixir:>2} | Hand: {h} | Gegner: {' | '.join(parts) or '-'}{foe}")

    # ---------- V: Verteidigen ----------
    def see(self, img) -> list[Unit]:
        """Alle Einheiten im Kampfbereich (Gegner und eigene). Ohne Modell: nur Gegner als „?“."""
        if self.detector is not None:
            try:
                return self.detector.detect(img)
            except Exception as e:
                print(f"  ⚠️  Einheiten-Erkennung ausgefallen ({type(e).__name__}: {e}). Spiele ohne Gegner-Namen.")
                self.detector = None
        units = []
        for badge in find_badges(img, self.p):
            ux, uy = badge_to_unit(badge)
            units.append(Unit("?", 0.0, (ux - 30, uy - 40, ux + 30, uy + 40), "enemy", "unknown", False, True, 3.0))
        return units

    def drop_static(self, units: list[Unit], now: float) -> list[Unit]:
        """Gebäude und alles, was auf der GEGNERSEITE länger unbewegt steht, ist keine Bedrohung."""
        keep = []
        for u in units:
            x, y = u.pos
            cell = (x // 40, y // 40)
            first, _ = self.seen_cells.get(cell, (now, now))
            self.seen_cells[cell] = (first, now)
            if u.kind == "building" or (y < self.bridge_y - 20 and now - first > STATIC_AFTER):
                continue
            keep.append(u)
        self.seen_cells = {c: v for c, v in self.seen_cells.items() if now - v[1] < 1.5}
        return keep

    @staticmethod
    def name_unknown(units: list[Unit]) -> list[Unit]:
        """Unerkannte Gegner direkt neben erkannten sind fast immer dieselbe Sorte (Schwärme kommen im Pulk)."""
        named = [u for u in units if u.name != "?"]
        out = []
        for u in units:
            if u.name == "?" and named:
                near = min(named, key=lambda n: (n.pos[0] - u.pos[0]) ** 2 + (n.pos[1] - u.pos[1]) ** 2)
                if (near.pos[0] - u.pos[0]) ** 2 + (near.pos[1] - u.pos[1]) ** 2 <= 110 ** 2 and near.cost <= 2:
                    u = Unit(near.name, 0.0, u.box, "enemy", near.kind, near.air, near.hits_air, near.cost)
            out.append(u)
        return out

    def update_towers(self, img, now: float):
        for name, hp in read_towers(img, self.p).items():
            if hp is None:
                self.tower_gone.setdefault(name, now)
                if now - self.tower_gone[name] > 6:        # länger kein Balken: Turm ist zerstört
                    self.towers[name] = 0.0
            else:
                self.tower_gone.pop(name, None)
                hist = self.tower_hist.setdefault(name, [])
                hist.append(hp)
                del hist[:-5]
                self.towers[name] = sorted(hist)[len(hist) // 2]   # Median: einzelne Fehlablesungen glätten

    def weaker_enemy_lane(self) -> str | None:
        """Spur mit dem schwächeren, noch stehenden gegnerischen Turm (bei klarem Unterschied)."""
        left, right = self.towers.get("enemy_left"), self.towers.get("enemy_right")
        if left is None or right is None or left <= 0 or right <= 0:
            return None
        if abs(left - right) < 0.12:
            return None
        return "left" if left < right else "right"

    def by_lane(self, enemies: list[Unit]) -> dict[str, list[Unit]]:
        lanes: dict[str, list[Unit]] = {}
        for u in enemies:
            lanes.setdefault("left" if u.pos[0] < self.mid_x else "right", []).append(u)
        return lanes

    def defend(self, lane: str, units: list[Unit], hand, elixir) -> bool:
        """Eine Antwort auf die gefährlichste noch unbeantwortete Gegnergruppe dieser Spur spielen."""
        now = time.time()
        tower_y = self.p[f"defend_{lane}"][1]
        self.spent[lane] = [(t, e) for t, e in self.spent[lane] if now - t < DEFEND_WINDOW]
        self.answered[lane] = [(t, n) for t, n in self.answered[lane] if now - t < ANSWER_MEMORY]
        front = max(u.pos[1] for u in units)
        at_tower = front > tower_y - 60
        budget = sum(u.cost for u in units) + (2.5 if at_tower else 1.0)   # nicht mehr ausgeben als der Gegner
        if sum(e for _, e in self.spent[lane]) >= budget:
            return False

        units = self.name_unknown(units)
        groups: dict[str, list[Unit]] = {}
        for u in units:
            groups.setdefault(u.name, []).append(u)
        done = [n for _, n in self.answered[lane]]
        spell_ready = now - self.last_spell[lane] >= SPELL_COOLDOWN
        for name, group in sorted(groups.items(), key=lambda kv: max(u.pos[1] for u in kv[1]), reverse=True):
            if name in done and not at_tower:
                continue
            g_front = max(u.pos[1] for u in group)
            early = 200 if any(u.fast for u in group) else 140 if self.style["defend_early"] else 40
            crossed = g_front >= self.bridge_y - early
            answer = choose(group, units, hand, elixir, at_tower, spell_ready)
            if answer is None:
                continue
            card, mode, target, why = answer
            if mode == "spell":
                if target[1] < self.bridge_y - 120:        # Gruppe noch tief drüben: warten
                    continue
                self.last_spell[lane] = now
                spot, own_side = (target[0], target[1] + 50), False
            elif not crossed:
                continue                                   # noch drüben: Elixier sparen, kommen lassen
            else:
                lead = max(group, key=lambda u: u.pos[1])
                spot = {"on": self.spot_on(lead), "front": self.spot_in_front(lane, g_front),
                        "behind": self.spot_behind(lane)}[mode]
                own_side = True
            self.spent[lane].append((now, card.cost))
            self.answered[lane].append((now, name))
            where = "links" if lane == "left" else "rechts"
            return self.play(card, spot, f"{why} {where}", own_side)

        if at_tower and not self.spent[lane]:              # Gegner am Turm und keine passende Karte: irgendwas
            if c := self.affordable(hand, elixir, lambda c: c.role in ("troop", "tank")):
                self.spent[lane].append((now, c[0].cost))
                return self.play(c[0], self.spot_in_front(lane, front - 150), f"Notlösung am Turm {lane}")
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
        foe_low = self.tracker is not None and self.tracker.elixir <= 3 and elixir >= 6
        if elixir < self.style["attack_at"] and not foe_low:
            return False
        if not pushing and now - max(self.last_defend.values()) > 10:
            lane = self.push_lane = self.weaker_enemy_lane() or lane   # schwächeren Turm angreifen
        note = " – Gegner hat wenig Elixier" if foe_low and elixir < self.style["attack_at"] else ""

        if c := self.affordable(hand, elixir, lambda c: c.role == "tank"):
            spots = {"back": (self.spot_back(lane), "hinten aufbauen"),
                     "tower": (self.spot_behind(lane), "neben dem Turm"),
                     "bridge": (self.spot_bridge(lane), "direkt an der Brücke")}
            spot, how = spots.get(self.style["tank_spot"]) or random.choice(list(spots.values()))
            self.push_until = now + PUSH_SECONDS
            return self.play(c[0], spot, f"Tank startet Angriff {lane} ({how}){note}")
        if c := self.affordable(hand, elixir, lambda c: c.role == "troop"):
            card = c[-1]
            if "ranged" in tags(card):
                spot, how = self.spot_back(lane), "Fernkämpfer hinten"
            else:
                spot, how = random.choice([(self.spot_bridge(lane), "Brücke"), (self.spot_back(lane), "hinten")])
            self.push_until = now + PUSH_SECONDS / 2
            return self.play(card, spot, f"Angriff {lane} ({how}){note}")
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
        now = time.time()
        units = self.see(img)
        all_enemies = [u for u in units if u.side == "enemy"]
        if self.tracker is None:
            self.tracker = EnemyTracker(now)
        for name in self.tracker.observe(all_enemies, now):
            print(f"  👁  Gegner spielt {de(name)} – ihm bleiben etwa {self.tracker.elixir:.0f} Elixier")
        self.update_towers(img, now)
        enemies = self.drop_static(all_enemies, now)
        threats = self.by_lane(enemies)
        if self.rec:
            self.rec.state(img, elixir, hand, units, {"enemy_elixir": round(self.tracker.elixir, 1),
                                                       "towers": self.towers})
        self.status(elixir, hand, threats)
        return self.decide(hand, elixir, threats)

    def decide(self, hand, elixir, threats: dict[str, list[Unit]]) -> bool:
        now = time.time()
        for lane, units in sorted(threats.items(), key=lambda kv: max(u.pos[1] for u in kv[1]), reverse=True):
            if now - self.last_defend[lane] < LANE_COOLDOWN:
                continue
            if self.defend(lane, units, hand, elixir):
                self.last_defend[lane] = time.time()
                self.push_lane = lane                      # K: Konter auf derselben Spur
                return True

        if now >= self.push_until and not threats and random.random() < 0.02:
            self.push_lane = random.choice(["left", "right"])
        return self.attack(hand, elixir)


def run(device: Device, points: dict):
    bot = RuleBot(device, points)
    if not bot.hand_reader.templates:
        raise SystemExit("Noch keine Karten bekannt. Erst: collect, dann label.")
    print(f"🧠 Regel-Bot läuft (V-K-P){', mit Gegner-Erkennung' if bot.detector else ''}. Stoppen mit Strg+C.")
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
    detector = load_detector(points, reader.info)
    print(f"♾️  Dauerbetrieb mit {len(nav.buttons)} Knöpfen"
          f"{' und Gegner-Erkennung' if detector else ''}. Stoppen mit Strg+C.")
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
                    bot = RuleBot(device, points, style, reader, detector)
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
