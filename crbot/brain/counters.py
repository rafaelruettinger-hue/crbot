"""Welche unserer Karten passt gegen welche gegnerische Einheit?

Grundregeln (Merkhilfe „L-N-F“ – Luft, Nah, Fläche):
  L  Fliegt der Gegner, helfen nur Karten, die in die LUFT schießen (Musketierin, Bogenschützen, Lakaien).
  N  Gegen einzelne starke Bodeneinheiten: NAH ran – Mini-P.E.K.K.A auf den Tank, Ritter auf Fernkämpfer.
     Lakaien sind stark gegen alles, was nicht in die Luft schlagen kann (Ritter, Riese, Walküre, Prinz …).
  F  Gegen viele kleine Einheiten: FLÄCHE – Pfeile auf Skelette/Kobolde/Lakaien, Feuerball auf Barbaren
     oder auf wertvolle Fernkämpfer (Musketierin, Magier, Hexe).
"""
import unicodedata

# Unsere Karten (Name wie beim Benennen) -> Fähigkeiten. Unbekannte Namen nutzen nur ihre Rolle.
TAGS = {
    "pfeile": {"swarm_spell"}, "zap": {"swarm_spell"}, "knall": {"swarm_spell"},
    "feuerball": {"area_spell"}, "gift": {"area_spell"},
    "minipekka": {"killer", "melee"}, "pekka": {"killer", "melee"}, "prinz": {"killer", "melee"},
    "ritter": {"melee"}, "walkuere": {"melee", "splash"}, "walküre": {"melee", "splash"},
    "kobolde": {"melee"}, "skelette": {"melee"},
    "musketier": {"ranged", "ranged_single"}, "musketierin": {"ranged", "ranged_single"},
    "bogenschützen": {"ranged"}, "bogenschuetzen": {"ranged"}, "speerkobolde": {"ranged"},
    "magier": {"ranged", "splash"}, "babydrache": {"ranged", "splash"}, "bomber": {"ranged", "splash"},
    "lakaien": {"ranged", "air_swarm"}, "fledermäuse": {"ranged", "air_swarm"},
}

# Art des Gegners -> unsere Antworten in Reihenfolge der Vorliebe
PREFS = {
    "air":           ["ranged_single", "ranged", "air_swarm"],
    "air_splash":    ["ranged_single", "ranged"],
    "small_air":     ["swarm_spell", "ranged", "air_swarm"],
    "small":         ["swarm_spell", "melee", "ranged", "air_swarm", "killer"],
    "horde":         ["area_spell", "air_swarm", "melee", "ranged", "killer"],
    "tank":          ["killer", "air_swarm", "ranged_single", "melee", "ranged"],
    "ranged":        ["melee", "killer", "area_spell", "air_swarm", "ranged"],
    "ranged_splash": ["melee", "killer", "area_spell", "ranged_single"],
    "melee":         ["air_swarm", "killer", "melee", "ranged_single", "ranged"],
    "melee_splash":  ["air_swarm", "killer", "ranged_single", "melee"],
    "unknown":       ["melee", "ranged", "killer"],
}

# Wie wird die Antwort gelegt?  on = direkt auf den Gegner, front = ihm in den Weg,
# behind = geschützt neben unseren Turm, spell = Zauber auf die Gruppe
MODE = {"killer": "on", "melee": "front", "ranged": "behind", "ranged_single": "behind",
        "air_swarm": "on", "swarm_spell": "spell", "area_spell": "spell"}

SMALL_KINDS = {"small", "small_air"}
SPELL_VALUE_KINDS = {"small", "small_air", "horde", "ranged", "ranged_splash"}

GERMAN = {
    "giant": "Riese", "knight": "Ritter", "archer": "Bogenschützen", "musketeer": "Musketierin",
    "minion": "Lakaien", "goblin": "Kobolde", "spear_goblin": "Speerkobolde", "skeleton": "Skelette",
    "valkyrie": "Walküre", "minipekka": "Mini-P.E.K.K.A", "bomber": "Bomber", "baby_dragon": "Babydrache",
    "prince": "Prinz", "dark_prince": "Dunkler Prinz", "witch": "Hexe", "wizard": "Magier",
    "hog_rider": "Schweinereiter", "balloon": "Ballon", "pekka": "P.E.K.K.A", "barbarian": "Barbaren",
    "elite_barbarian": "Elitebarbaren", "bat": "Fledermäuse", "royal_giant": "Königsriese", "golem": "Golem",
    "mega_minion": "Megalakai", "brawler": "Kobold-Schläger", "goblin_hut": "Koboldhütte",
    "tombstone": "Grabstein", "goblin_cage": "Koboldkäfig", "cannon": "Kanone", "battle_ram": "Rammbock",
    "mega_knight": "Megaritter", "giant_skeleton": "Riesenskelett", "ice_golem": "Eisgolem",
    "dart_goblin": "Blasrohrkobold", "bandit": "Banditin", "miner": "Bergarbeiter", "princess": "Prinzessin",
    "inferno_dragon": "Infernodrache", "lava_hound": "Lavahund", "electro_wizard": "Elektromagier",
    "ice_wizard": "Eismagier", "lumberjack": "Holzfäller", "fire_spirit": "Feuergeist", "ice_spirit": "Eisgeist",
    "?": "unbekannt",
}


def norm(name: str) -> str:
    return unicodedata.normalize("NFC", name).lower()


def card_tags(card) -> set:
    return TAGS.get(norm(card.name), set())


def de(name: str) -> str:
    return GERMAN.get(name, name)


def near(units: list, centre, radius: int = 120) -> list:
    cx, cy = centre
    return [u for u in units if (u.pos[0] - cx) ** 2 + (u.pos[1] - cy) ** 2 <= radius ** 2]


def spell_ok(tag: str, group: list, lane_units: list, at_tower: bool) -> tuple[bool, tuple, str]:
    """Lohnt sich der Zauber? -> (ja/nein, Zielpunkt, Begründung)"""
    centre = (sum(u.pos[0] for u in group) // len(group), sum(u.pos[1] for u in group) // len(group))
    hit = near(lane_units, centre)
    if tag == "swarm_spell":
        small = [u for u in hit if u.kind in SMALL_KINDS or u.name == "?"]
        need = 2 if at_tower else 3
        return len(small) >= need, centre, f"{len(small)} kleine Einheiten"
    value = sum(u.cost for u in hit if u.kind in SPELL_VALUE_KINDS)
    need = 3.0 if at_tower else 4.0
    return value >= need, centre, f"Wert {value:.0f} Elixier"


def choose(group: list, lane_units: list, hand: list, elixir: int, at_tower: bool, spell_ready: bool):
    """Beste Antwort auf eine Gruppe gleicher Gegner.
    -> (Karte, Art des Legens, Zauber-Ziel oder None, Begründung) oder None"""
    kind = group[0].kind
    for tag in PREFS.get(kind, PREFS["unknown"]):
        cards = sorted((c for c in hand if c.name != "?" and c.cost <= elixir and tag in card_tags(c)),
                       key=lambda c: c.cost)
        if tag == "melee" and kind in ("small", "horde"):
            cards = [c for c in cards if "killer" not in card_tags(c)]   # Einzelziel-Killer nicht an Kleinvieh verschwenden
        if not cards:
            continue
        mode, target, extra = MODE[tag], None, ""
        if mode == "spell":
            if not spell_ready:
                continue
            ok, target, extra = spell_ok(tag, group, lane_units, at_tower)
            if not ok:
                continue
        if tag == "melee" and kind in ("ranged", "ranged_splash"):
            mode = "on"                                   # Fernkämpfer: direkt drauf, nicht davor
        if tag == "air_swarm" and any(u.hits_air and u.kind.endswith("splash") for u in group):
            continue                                      # Flächenschaden in die Luft frisst Lakaien
        n = len(group)
        who = f"{n}× {de(group[0].name)}" if n > 1 else de(group[0].name)
        return cards[0], mode, target, f"gegen {who}" + (f" ({extra})" if extra else "")
    return None
