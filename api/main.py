from contextlib import asynccontextmanager
from threading import Thread
import os
import time
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from diamond.config import DATA_DIR, DB_PATH, cors_origins, ingest_years
from diamond.db import connect
from diamond.routes import router

LOCK_PATH = DATA_DIR / "ingest.lock"


def _log(message: str) -> None:
    print(message, flush=True)


def _ingest_complete() -> bool:
    if not DB_PATH.exists():
        return False
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='ingest_complete'").fetchone()
        return bool(row and str(row[0]) == "1")
    except Exception:
        return False
    finally:
        conn.close()


def _player_count() -> int:
    if not DB_PATH.exists():
        return 0
    conn = connect()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
    except Exception:
        return 0
    finally:
        conn.close()


def _clear_stale_lock() -> None:
    """A lock on disk after boot is leftover from a killed ingest (OOM/redeploy)."""
    if LOCK_PATH.exists():
        _log(f"Removing stale ingest lock {LOCK_PATH}")
        LOCK_PATH.unlink(missing_ok=True)


def _ingest_if_empty() -> None:
    if _ingest_complete():
        _log("Skip ingest; ingest_complete=1")
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        _log(f"Skip ingest; lock already present at {LOCK_PATH}")
        return
    try:
        if _ingest_complete():
            _log("Skip ingest; ingest_complete=1")
            return
        from diamond.ingest import run_ingest

        years = ingest_years()
        resume = DB_PATH.exists()
        _log(f"Ingesting MLB Stats API data for {years} (resume={resume} players={_player_count()})")
        run_ingest(years, resume=resume)
        _log("Ingest finished")
    except Exception:
        traceback.print_exc()
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def _boot_ingest() -> None:
    _log("Boot ingest thread sleeping 20s")
    time.sleep(20)
    _ingest_if_empty()


def _hands_needed() -> bool:
    if not DB_PATH.exists():
        return False
    conn = connect()
    try:
        n = int(conn.execute("SELECT COUNT(*) FROM players WHERE throws IN ('L', 'R')").fetchone()[0])
        return n < 50
    except Exception:
        return True
    finally:
        conn.close()


def _boot_hands() -> None:
    time.sleep(8)
    try:
        from diamond.hands import enrich_hands

        conn = connect()
        try:
            n = enrich_hands(conn)
            _log(f"Handedness enrich finished ({n} people updated)")
        finally:
            conn.close()
    except Exception:
        traceback.print_exc()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"Could not create data dir {DATA_DIR}: {exc}")
    _clear_stale_lock()
    if _ingest_complete():
        _log(f"No boot ingest needed (ingest_complete=1 players={_player_count()})")
        if _hands_needed():
            _log("Starting handedness enrich thread")
            Thread(target=_boot_hands, daemon=True).start()
    else:
        _log(f"Starting ingest thread (db={DB_PATH.exists()} players={_player_count()})")
        Thread(target=_boot_ingest, daemon=True).start()
    yield


app = FastAPI(title="Diamond", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "diamond-api",
        "health": "/health",
        "meta": "/api/meta",
    }
