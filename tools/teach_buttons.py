"""Dem Bot die Menü-Knöpfe zeigen: Du klickst den Weg einmal im Fenster durch,
das Werkzeug merkt sich jeden Knopf und drückt ihn für dich im Emulator.

Start am besten auf dem ENDBILDSCHIRM eines Kampfes (dort, wo der OK-Knopf ist)."""
import time

import cv2

from crbot.device import Device
from crbot.nav import BUTTONS_DIR, BUTTONS_FILE, load_list, save_button

WAIT_AFTER_TAP = 2.5


def main(reset: bool = False):
    dev = Device.load()
    if reset:
        if BUTTONS_DIR.exists():
            for p in BUTTONS_DIR.glob("*.png"):
                p.unlink()
        BUTTONS_FILE.unlink(missing_ok=True)
    buttons = load_list()
    print("Im Fenster (Cmd+Tab -> Python): den Knopf anklicken, den der Bot druecken soll.")
    print("Ich druecke ihn dann im Emulator und zeige das naechste Bild.")
    print("Leertaste = neues Bild (wenn der Bildschirm noch laedt) · ESC = fertig\n")
    win = "Knoepfe beibringen - Klick = Knopf, Leertaste = neues Bild, ESC = fertig"
    click = {}
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, lambda e, x, y, *_: click.update(pos=(x, y)) if e == cv2.EVENT_LBUTTONDOWN else None)
    try:
        cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass
    done = False
    while not done:
        img = dev.screenshot()
        scale = 900 / img.shape[0] if img.shape[0] > 900 else 1.0
        view = cv2.resize(img, None, fx=scale, fy=scale)
        cv2.rectangle(view, (0, 0), (view.shape[1], 34), (0, 0, 0), -1)
        cv2.putText(view, f"Knopf {len(buttons) + 1}: anklicken", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imshow(win, view)
        click.clear()
        while True:
            key = cv2.waitKey(50)
            if key == 27:
                done = True
                break
            if key == 32:
                break
            if "pos" in click:
                x, y = int(click["pos"][0] / scale), int(click["pos"][1] / scale)
                entry = save_button(img, x, y, buttons)
                print(f"  ✅ {entry['name']} bei ({x}, {y}) gemerkt – druecke ihn jetzt")
                dev.tap(x, y)
                time.sleep(WAIT_AFTER_TAP)
                break
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    print(f"💾 {len(buttons)} Knoepfe gespeichert. Dauerbetrieb starten: uv run python -m crbot.main auto")
