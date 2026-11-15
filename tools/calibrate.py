"""Punkte per Klick auf einem Screenshot einmessen -> config/points.json.
Am besten mitten in einem Trainingslager-Kampf ausführen."""
import json

import cv2

from crbot.device import Device
from crbot.paths import CONFIG_DIR, POINTS_FILE

CALIB_POINTS = [
    ("card1", "Mitte Karte 1 (Hand, ganz links)"),
    ("card2", "Mitte Karte 2"),
    ("card3", "Mitte Karte 3"),
    ("card4", "Mitte Karte 4 (ganz rechts)"),
    ("elixir_start", "LINKER Anfang des Elixierbalkens"),
    ("elixir_end", "RECHTES Ende des Elixierbalkens"),
    ("bridge_left", "Eigene Seite, kurz vor der LINKEN Bruecke"),
    ("bridge_right", "Eigene Seite, kurz vor der RECHTEN Bruecke"),
    ("defend_left", "Verteidigung links (vor deinem linken Turm)"),
    ("defend_right", "Verteidigung rechts (vor deinem rechten Turm)"),
    ("behind_king", "Hinter deinem Koenigsturm (Mitte unten)"),
]


def main():
    img = Device.load().screenshot()
    h, w = img.shape[:2]
    scale = 900 / h if h > 900 else 1.0
    view = cv2.resize(img, (int(w * scale), int(h * scale)))
    points = json.loads(POINTS_FILE.read_text()) if POINTS_FILE.exists() else {}
    state = {"i": 0}
    win = "Kalibrierung - Punkt anklicken, ESC = abbrechen"

    def draw():
        canvas = view.copy()
        for name, (px, py) in points.items():
            p = (int(px * scale), int(py * scale))
            cv2.circle(canvas, p, 6, (0, 255, 0), -1)
            cv2.putText(canvas, name, (p[0] + 8, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        if state["i"] < len(CALIB_POINTS):
            cv2.putText(canvas, CALIB_POINTS[state["i"]][1], (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        cv2.imshow(win, canvas)

    def on_click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and state["i"] < len(CALIB_POINTS):
            name = CALIB_POINTS[state["i"]][0]
            points[name] = [int(x / scale), int(y / scale)]
            print(f"  {name} = {points[name]}")
            state["i"] += 1
            draw()

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    draw()
    while state["i"] < len(CALIB_POINTS):
        if cv2.waitKey(50) == 27:
            break
    cv2.waitKey(800)
    cv2.destroyAllWindows()
    CONFIG_DIR.mkdir(exist_ok=True)
    POINTS_FILE.write_text(json.dumps(points, indent=2))
    print(f"💾 {len(points)} Punkte gespeichert in {POINTS_FILE}")


if __name__ == "__main__":
    main()
