"""Aus den aufgezeichneten Kämpfen lernen, welcher Spielstil häufiger gewinnt.

Verfahren (Thompson Sampling, ein „mehrarmiger Bandit“): Für jede Stellschraube wird gezählt,
wie gut die Kämpfe mit jedem Wert liefen. Vor jedem Kampf wird für jeden Wert aus dieser
Erfahrung „gewürfelt“ – bewährte Werte gewinnen den Wurf immer öfter, selten probierte
bekommen aber weiter Chancen. So wird der Bot besser, ohne sich zu früh festzulegen.
"""
import json
import random

import cv2

from crbot.brain.rules import STYLE_CHOICES
from crbot.recorder import GAMES_DIR
from crbot.vision.result import read_result


def load_games() -> list[dict]:
    """Alle Kämpfe mit bekanntem Ergebnis. Fehlende Ergebnisse werden aus end.png nachgetragen."""
    games = []
    if not GAMES_DIR.exists():
        return games
    for d in sorted(GAMES_DIR.iterdir()):
        meta_file = d / "meta.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text())
        if not meta.get("result") and (d / "end.png").exists():
            res = read_result(cv2.imread(str(d / "end.png")))
            if res:
                meta["result"] = res
                meta_file.write_text(json.dumps(meta, indent=2))
        if meta.get("result") and meta.get("style"):
            games.append(meta)
    return games


def tally(games: list[dict]) -> dict:
    """{Stellschraube: {Wert: [Belohnungssumme, Anzahl, Siege]}}"""
    t = {k: {v: [0.0, 0, 0] for v in vals} for k, vals in STYLE_CHOICES.items()}
    for g in games:
        for k, v in g["style"].items():
            if k in t and v in t[k]:
                cell = t[k][v]
                cell[0] += g["result"]["reward"]
                cell[1] += 1
                cell[2] += g["result"]["result"] == "win"
    return t


def choose_style(games: list[dict]) -> dict:
    style = {}
    for k, cells in tally(games).items():
        draws = {v: random.betavariate(1 + r, 1 + n - r) for v, (r, n, _) in cells.items()}
        style[k] = max(draws, key=draws.get)
    return style


def best_style(games: list[dict]) -> dict:
    return {k: max(cells, key=lambda v: (1 + cells[v][0]) / (2 + cells[v][1]))
            for k, cells in tally(games).items()}


def summary(games: list[dict]) -> str:
    if not games:
        return "Noch keine ausgewerteten Kämpfe."
    wins = sum(g["result"]["result"] == "win" for g in games)
    lines = [f"📊 {len(games)} Kämpfe ausgewertet: {wins} Siege, {len(games) - wins} Niederlagen "
             f"({100 * wins // len(games)} %)"]
    for k, cells in tally(games).items():
        parts = [f"{v}: {w}/{n}" for v, (_, n, w) in cells.items()]
        lines.append(f"   {k:<13} " + "   ".join(parts) + "   (Siege/Kämpfe)")
    lines.append(f"   Bisher bester Stil: {best_style(games)}")
    return "\n".join(lines)
