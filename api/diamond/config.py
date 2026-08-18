import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "diamond.db"

SEASONS = list(range(2022, 2027))
REGULAR_PA = 20
REGULAR_IP = 6.0
REGULAR_LOOKBACK_GAMES = 15
TEAM_LOOKBACK_GAMES = 30
TEAM_RECENT_GAMES = 10
HTTP_WORKERS = int(os.environ.get("HTTP_WORKERS", "4"))


def ingest_years() -> list[int]:
    raw = os.environ.get("INGEST_SEASONS", "")
    if raw.strip():
        return [int(part.strip()) for part in raw.split(",") if part.strip()]
    return SEASONS


HOSTGATOR_ORIGINS = (
    "https://theprofitengineer.com",
    "https://www.theprofitengineer.com",
)


def cors_origins() -> list[str]:
    raw = os.environ.get(
        "CORS_ORIGINS",
        "http://127.0.0.1:5174,http://localhost:5174",
    )
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    for origin in HOSTGATOR_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    return origins
