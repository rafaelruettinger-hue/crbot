"""ADB-Anbindung an den Emulator (MuMu Player Pro): verbinden, Screenshot, Tap."""
import json
import subprocess
import time

import cv2
import numpy as np

from crbot.paths import CONFIG_DIR

DEVICE_FILE = CONFIG_DIR / "device.json"

# Typische ADB-Ports von MuMu (Pro/12) und anderen Emulatoren
CANDIDATE_PORTS = [16384, 16416, 16448, 7555, 5555, 5556]
EXPECTED_SIZE = "900x2000"
SHOT_TIMEOUT = 4  # Sekunden; normal dauert ein Screenshot ~0,4 s


def adb(*args, serial=None, binary=False, timeout=20):
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"ADB-Fehler: {' '.join(cmd)}\n{res.stderr.decode(errors='ignore')}")
    return res.stdout if binary else res.stdout.decode(errors="ignore").strip()


def decode_raw(raw: bytes) -> np.ndarray:
    """screencap-Rohformat: Header (12 oder 16 Byte) + RGBA-Pixel."""
    if len(raw) < 16:
        raise RuntimeError("Leerer Screenshot – läuft das Gerät?")
    w, h = int.from_bytes(raw[0:4], "little"), int.from_bytes(raw[4:8], "little")
    header = len(raw) - w * h * 4
    if header not in (12, 16):
        raise RuntimeError(f"Unerwartetes Screenshot-Format ({w}x{h}, Header {header}).")
    rgba = np.frombuffer(raw, np.uint8, offset=header).reshape(h, w, 4)
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)


class Device:
    def __init__(self, serial: str):
        self.serial = serial

    @classmethod
    def load(cls) -> "Device":
        if not DEVICE_FILE.exists():
            raise SystemExit("Noch nicht verbunden. Zuerst: uv run python -m crbot.main connect")
        dev = cls(json.loads(DEVICE_FILE.read_text())["serial"])
        dev.ensure_connected()
        return dev

    def ensure_connected(self):
        """Nach einem MuMu-Neustart ist die ADB-Verbindung weg – dann still neu verbinden."""
        try:
            state = adb("get-state", serial=self.serial, timeout=5)
            if state == "device":
                return
        except Exception:
            pass
        try:
            adb("connect", self.serial, timeout=5)
            if adb("get-state", serial=self.serial, timeout=5) == "device":
                print(f"🔌 Neu verbunden mit {self.serial}")
                return
        except Exception:
            pass
        raise SystemExit("❌ Emulator nicht erreichbar. Läuft das MuMu-Gerät? Sonst: uv run python -m crbot.main connect")

    @classmethod
    def connect(cls) -> "Device | None":
        for port in CANDIDATE_PORTS:
            addr = f"127.0.0.1:{port}"
            try:
                out = adb("connect", addr, timeout=5)
                if "connected" not in out or "cannot" in out:
                    continue
                size = adb("shell", "wm", "size", serial=addr, timeout=5)
            except Exception:
                continue
            CONFIG_DIR.mkdir(exist_ok=True)
            DEVICE_FILE.write_text(json.dumps({"serial": addr}, indent=2))
            print(f"✅ Verbunden mit {addr}  ({size})")
            if EXPECTED_SIZE not in size:
                print(f"⚠️  Auflösung ist nicht {EXPECTED_SIZE} – bitte in MuMu umstellen.")
            return cls(addr)
        print("❌ Kein Emulator gefunden. Läuft MuMu? ADB-Port in MuMu prüfen und in CANDIDATE_PORTS eintragen.")
        return None

    def screenshot(self, tries: int = 4) -> np.ndarray:
        """Rohdaten statt PNG (schneller). Der Emulator hängt gelegentlich:
        kurzes Zeitlimit, dann neu verbinden und noch einmal versuchen."""
        last = None
        for attempt in range(tries):
            try:
                raw = adb("exec-out", "screencap", serial=self.serial, binary=True, timeout=SHOT_TIMEOUT)
                return decode_raw(raw)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                last = e
                if attempt >= 1:  # beim zweiten Fehlschlag Verbindung frisch aufbauen
                    self.reconnect()
                time.sleep(0.3)
        raise RuntimeError(f"Screenshot nach {tries} Versuchen fehlgeschlagen: {last}")

    def reconnect(self):
        for args in (("disconnect", self.serial), ("connect", self.serial)):
            try:
                adb(*args, timeout=5)
            except Exception:
                pass

    def screenshot_png(self) -> np.ndarray:
        raw = adb("exec-out", "screencap", "-p", serial=self.serial, binary=True)
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Screenshot konnte nicht gelesen werden.")
        return img

    def tap(self, x: int, y: int):
        adb("shell", "input", "tap", str(int(x)), str(int(y)), serial=self.serial)
