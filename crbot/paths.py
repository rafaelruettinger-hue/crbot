from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
SHOTS_DIR = DATA_DIR / "shots"
MODELS_DIR = ROOT / "models"
POINTS_FILE = CONFIG_DIR / "points.json"
