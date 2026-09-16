from pathlib import Path


# Raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent


# Directorios de datos
DATA_DIR = BASE_DIR / "data"

INPUT_DIR = DATA_DIR / "input"

PROCESSED_DIR = DATA_DIR / "processed"

OUTPUT_DIR = DATA_DIR / "output"