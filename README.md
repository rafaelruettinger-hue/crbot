# crbot

Eigener Clash-Royale-Bot als Lernprojekt – läuft in **MuMu Player Pro** auf dem Mac (Apple Silicon).
Nur für Trainingslager und Freundschaftskämpfe gedacht.

## Einrichtung (einmalig)

```bash
brew install git gh python@3.12 uv android-platform-tools
gh repo clone rafaelruettinger-hue/crbot && cd crbot
uv sync
```

MuMu-Gerät: **900 × 2000, DPI 300, Root an**, Clash Royale aus dem **Google Play Store**.

## Benutzung

```bash
uv run python -m crbot.main connect    # Emulator verbinden
uv run python -m crbot.main shot       # Screenshot
uv run python -m crbot.main calib      # Punkte einmessen (im Trainingslager-Kampf)
uv run python -m crbot.main elixir     # Elixier-Erkennung testen
uv run python -m crbot.main run        # Zufalls-Bot (Stufe 1)

# Stufe 2
uv run python -m crbot.main collect    # Handkarten sammeln (während du selbst spielst)
uv run python -m crbot.main label      # Karten benennen (Name, Kosten, Rolle)
uv run python -m crbot.main see        # was erkennt der Bot? -> data/shots/debug.png
uv run python -m crbot.main play       # Regel-Bot, ein Kampf

# Dauerbetrieb (Trainingscamp)
uv run python -m crbot.main teach      # Menü-Knöpfe zeigen (einmalig)
uv run python -m crbot.main auto       # spielt Kampf für Kampf, schreibt mit (data/games/) und lernt den besten Stil
uv run python -m crbot.main stats      # Auswertung: Siege je Spielstil
```

## Aufbau

```
crbot/device.py      ADB: verbinden, Screenshot, Tap
crbot/vision/        Erkennen: Elixier, (bald) Karten & Einheiten
crbot/brain/         Entscheiden: erst Regeln, später KI
crbot/main.py        Einstiegspunkt
tools/               Kalibrierung & Hilfsskripte
config/              points.json (eingemessene Punkte)
data/, models/       Screenshots & Modelle – nicht auf GitHub
```

## Fahrplan

- [x] **Stufe 1** – Grundgerüst: verbinden, Screenshot, Elixier, Mini-Bot
- [x] **Stufe 2** – Sehen: Handkarten ✅, Gegner per rotem Level-Abzeichen ✅, Einheiten-Erkennung per YOLO-Modell ✅ (Modell aus ClashRoyaleBuildABot, MIT)
- [~] **Stufe 3** – Regel-Bot „V-K-P“ ✅, passende Antwort je Gegnerkarte („L-N-F“, siehe crbot/brain/counters.py) ✅, Elixier des Gegners mitzählen (offen)
- [ ] **Stufe 4** – Imitation Learning aus Replays (Ideen/Daten: KataCR)
- [ ] **Stufe 5** – Reinforcement Learning
- [ ] **Stufe 6** – Feinschliff

## Log

- **2026-11-15** – Projekt angelegt, Stufe-1-Code geschrieben.
- **2026-11-16** – Stufe 1 läuft (kalibriert, Zufalls-Bot spielt). Stufe 2: schnellere Screenshots, Auto-Reconnect, Kartenerkennung, Gegnererkennung, Regel-Bot V-K-P.
- **2026-11-16** – Gegner per Level-Abzeichen, Karten verschiebungstolerant, Dauerbetrieb (teach/auto), Rekorder (data/games), Spielstil-Variation pro Kampf. Offen: Ergebnis aus end.png lesen -> besten Stil lernen.
- **2026-11-16** – Ergebnis vom Endbildschirm (Kronen zählen), Stil-Lernen per Thompson Sampling, jede Karte nur einmal pro Hand. Offen: Ergebnis-Erkennung mit echten end.png (auch Niederlage) prüfen; Gegnerzählung an echten Bildern prüfen.
- **2026-11-16** – Auswertung des ersten aufgezeichneten Kampfes: Kampf wird jetzt am Elixierbalken erkannt (keine Fehlstarts im Menü), Elixier 10 wird gelesen, Zauber nur auf enge Gruppen mit Pause, nicht mehr Verteidiger als nötig, unbewegte Ziele auf der Gegnerseite ignoriert.
- **2026-11-16** – Gegnerkarten erkennen: YOLO-Modell (97 Einheiten) eingebunden, Freund/Feind über rotes Abzeichen, Konter-Tabelle für das eigene Deck. Rekorder speichert jetzt alle erkannten Einheiten. Geprüft an 42 echten Kampfbildern; im laufenden Spiel noch zu testen.
- **2026-11-16** – Turm-Lebenspunkte lesen (Angriff auf den schwächeren Turm), Gegner mitzählen (gespielte Karten, geschätztes Elixier; Angriff, wenn der Gegner wenig hat). KataCR geprüft: Code und Bilddatensatz MIT; Replay-Datensatz nur für das Hog-2.6-Deck, daher für unser Deck nicht direkt nutzbar.
