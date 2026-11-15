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
uv run python -m crbot.main run        # Mini-Bot starten
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

- [ ] **Stufe 1** – Grundgerüst: verbinden, Screenshot, Elixier, Mini-Bot
- [ ] **Stufe 2** – Sehen: Handkarten, Türme, Einheiten (Basis: ClashRoyaleBuildABot, MIT)
- [ ] **Stufe 3** – Regel-Bot: Verteidigen, Konter, Elixier mitzählen
- [ ] **Stufe 4** – Imitation Learning aus Replays (Ideen/Daten: KataCR)
- [ ] **Stufe 5** – Reinforcement Learning
- [ ] **Stufe 6** – Feinschliff

## Log

- **2026-11-15** – Projekt angelegt, Stufe-1-Code geschrieben.
