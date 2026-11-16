"""Den Gegner mitzählen: Welche Karten hat er gespielt, wie viel Elixier hat er ungefähr noch?

Elixier wächst für beide Seiten gleich schnell (1 pro 2,8 s; in der letzten Minute doppelt).
Taucht eine neue gegnerische Einheit auf, hat der Gegner die Kosten ihrer Karte bezahlt.
Das ist eine Schätzung: Zauber sehen wir nicht, und nicht jede Einheit wird erkannt.
"""
from collections import deque

REGEN_SECONDS = 2.8
DOUBLE_AFTER, TRIPLE_AFTER = 120.0, 240.0      # Sekunden seit Kampfbeginn
START_ELIXIR = 5.0
REDEPLOY_GAP = 5.0                             # dieselbe Karte frühestens nach so vielen Sekunden erneut zählen
MEMORY = 4.0                                   # „war gerade schon da“-Fenster

# Kosten der KARTE, zu der eine erkannte Einheit gehört
CARD_COST = {
    "skeleton": 1, "ice_spirit": 1, "fire_spirit": 1, "electro_spirit": 1, "heal_spirit": 1,
    "goblin": 2, "spear_goblin": 2, "bat": 2, "bomber": 2, "ice_golem": 2, "wall_breaker": 2,
    "knight": 3, "archer": 3, "minion": 3, "mega_minion": 3, "dart_goblin": 3, "bandit": 3, "miner": 3,
    "princess": 3, "ice_wizard": 3, "royal_ghost": 3, "guard": 3, "tombstone": 3, "cannon": 3,
    "musketeer": 4, "minipekka": 4, "valkyrie": 4, "baby_dragon": 4, "hog_rider": 4, "battle_ram": 4,
    "inferno_dragon": 4, "electro_wizard": 4, "lumberjack": 4, "dark_prince": 4, "hunter": 4,
    "goblin_cage": 4, "brawler": 4, "tesla": 4, "goblin_hut": 4, "furnace": 4, "mortar": 4,
    "giant": 5, "prince": 5, "wizard": 5, "witch": 5, "balloon": 5, "barbarian": 5, "ram_rider": 5,
    "bowler": 5, "executioner": 5, "electro_dragon": 5, "royal_hog": 5, "inferno_tower": 5, "bomb_tower": 4,
    "royal_giant": 6, "giant_skeleton": 6, "sparky": 6, "elite_barbarian": 6, "x_bow": 6,
    "elixir_collector": 6, "barbarian_hut": 6, "pekka": 7, "mega_knight": 7, "lava_hound": 7,
    "electro_giant": 7, "royal_recruit": 7, "golem": 8,
}
# Diese Gebäude erzeugen laufend Einheiten – die kosten den Gegner nichts extra.
SPAWNS = {"goblin_hut": "spear_goblin", "tombstone": "skeleton", "furnace": "fire_spirit",
          "barbarian_hut": "barbarian", "goblin_cage": "brawler", "witch": "skeleton",
          "night_witch": "bat", "lava_hound": "lava_pup", "golem": "golemite"}


class EnemyTracker:
    def __init__(self, now: float):
        self.t0 = self.last = now
        self.elixir = START_ELIXIR
        self.cards: dict[str, int] = {}            # gesehene Karten -> wie oft gespielt
        self.recent: dict[str, deque] = {}         # Name -> (Zeit, Anzahl) der letzten Sekunden
        self.last_deploy: dict[str, float] = {}
        self.spawner_seen: dict[str, float] = {}   # erzeugte Einheit -> wann zuletzt ein Erzeuger stand
        self.pending: dict[str, int] = {}          # Name -> in wie vielen Bildern nacheinander neu gesehen

    def _regen(self, now: float):
        t, dt = now - self.t0, max(now - self.last, 0.0)
        rate = (3 if t >= TRIPLE_AFTER else 2 if t >= DOUBLE_AFTER else 1) / REGEN_SECONDS
        self.elixir = min(10.0, self.elixir + dt * rate)
        self.last = now

    def observe(self, enemies: list, now: float) -> list[str]:
        """Mit allen aktuell sichtbaren gegnerischen Einheiten aufrufen. -> neu gespielte Karten"""
        self._regen(now)
        counts: dict[str, int] = {}
        for u in enemies:
            if u.name != "?":
                counts[u.name] = counts.get(u.name, 0) + 1
        for name in counts:
            if name in SPAWNS:
                self.spawner_seen[SPAWNS[name]] = now
        played = []
        for name, n in counts.items():
            hist = self.recent.setdefault(name, deque())
            while hist and now - hist[0][0] > MEMORY:
                hist.popleft()
            before = max((c for _, c in hist), default=0)
            hist.append((now, n))
            from_spawner = now - self.spawner_seen.get(name, -1e9) < 12.0
            if n > before and not from_spawner and now - self.last_deploy.get(name, -1e9) > REDEPLOY_GAP:
                self.pending[name] = self.pending.get(name, 0) + 1
                if self.pending[name] >= 2 or before == 0 and n >= 2:   # bestätigt (zweimal gesehen oder Gruppe)
                    self.pending.pop(name, None)
                    self.last_deploy[name] = now
                    self.cards[name] = self.cards.get(name, 0) + 1
                    self.elixir = max(0.0, self.elixir - CARD_COST.get(name, 3))
                    played.append(name)
            else:
                self.pending.pop(name, None)
        return played
