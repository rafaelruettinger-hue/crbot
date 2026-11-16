"""Gesammelte Karten-Ausschnitte benennen -> config/cards/ + config/cards.json"""
import cv2

from crbot.vision.hand import CARDS_DIR, best_match, core, load_info, load_templates, nfc, save_info
from tools.collect_cards import UNKNOWN_DIR

ROLES = {"t": "tank", "n": "troop", "s": "spell", "b": "building"}
AUTO = 0.85


def ask_int(prompt, lo, hi):
    while True:
        v = input(prompt).strip()
        if v.isdigit() and lo <= int(v) <= hi:
            return int(v)
        print(f"  Bitte Zahl {lo}–{hi}.")


def main():
    files = sorted(UNKNOWN_DIR.glob("*.png")) if UNKNOWN_DIR.exists() else []
    if not files:
        print("Nichts zu benennen. Erst sammeln: uv run python -m crbot.main collect")
        return
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    info, templates = load_info(), load_templates()
    print(f"{len(files)} Ausschnitte. Im Fenster siehst du die Karte, hier im Terminal tippst du.")
    print("Name eingeben (z. B. ritter) · Enter = überspringen · x = löschen (Müll) · q = beenden\n")
    win = "Karte"
    for p in files:
        img = cv2.imread(str(p))
        if img is None:
            p.unlink()
            continue
        name, score = best_match(img, templates)
        if score >= AUTO:
            print(f"  {p.name}: automatisch = {name} ({score:.2f}) – gelöscht")
            p.unlink()
            continue
        cv2.imshow(win, cv2.resize(img, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_NEAREST))
        cv2.waitKey(400)
        ans = input(f"{p.name} (Vorschlag: {name} {score:.2f}) > ").strip().lower().replace(" ", "_")
        ans = nfc(ans)
        if ans == "q":
            break
        if ans == "x":
            p.unlink()
            continue
        if not ans:
            continue
        if ans not in info:
            cost = ask_int("  Elixierkosten (1–10)? ", 1, 10)
            role = ""
            while role not in ROLES:
                role = input("  Rolle? t = Tank, n = normale Truppe, s = Zauber, b = Gebäude > ").strip().lower()
            info[ans] = {"cost": cost, "role": ROLES[role]}
            save_info(info)
        n = len(list(CARDS_DIR.glob(f"{ans}__*.png"))) + 1
        target = CARDS_DIR / f"{ans}__{n}.png"
        p.rename(target)
        templates.append((ans, core(img)))
        print(f"  ✅ gespeichert als {target.name}")
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    print(f"Fertig. Bekannte Karten: {', '.join(sorted(info)) or '-'}")
